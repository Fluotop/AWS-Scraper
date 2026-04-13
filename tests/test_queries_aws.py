"""AWS Athena integration tests for the 4 SQL query files.

These tests run the SQL files against the live Athena database and compare
results against the snapshot CSVs in tests/data_dev/.

All tests are skipped automatically when AWS credentials are not configured.

Prerequisites:
  - AWS credentials available (env vars, ~/.aws/credentials, or IAM role)
  - The price_changes table already exists in Athena
    (created by lambda_prepare.py lambda_handler)
  - Environment variables (optional, fall back to defaults):
      DATABASE        – Glue/Athena database name  (default: scraper)
      OUTPUT_LOCATION – S3 prefix for Athena results
                        (default: s3://bdm060897-prod/scraper/athena-results/)
      AWS_REGION      – AWS region                 (default: us-east-1)

Run:
  pytest tests/test_queries_aws.py -v
  pytest tests/test_queries_aws.py -v -m aws        # if you add the marker
"""

import os
import time
from pathlib import Path

import polars as pl
import pytest

from conftest import SQL_DIR
import boto3

DATABASE        = os.environ.get("DATABASE",        "scraper")
OUTPUT_LOCATION = os.environ.get("OUTPUT_LOCATION", "s3://bdm060897-prod/scraper/athena-results/")
AWS_REGION      = os.environ.get("AWS_REGION",      "us-east-1")

DATA_DEV = Path(__file__).parent / "data_dev"

# ── Athena client fixture ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def athena():
    """Return a boto3 Athena client, or skip the entire session if unavailable."""

    client = boto3.client("athena", region_name=AWS_REGION)
    # Lightweight check – raises if credentials are missing/invalid
    client.list_work_groups()
    return client


# ── Athena helpers ────────────────────────────────────────────────────────────

def _run_query(athena_client, sql: str, result_prefix: str = "test/") -> str:
    resp = athena_client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": OUTPUT_LOCATION + result_prefix},
    )
    return resp["QueryExecutionId"]


def _wait(athena_client, execution_id: str, poll_interval: int = 2) -> None:
    while True:
        status = athena_client.get_query_execution(
            QueryExecutionId=execution_id
        )["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            return
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(
                f"Athena query {execution_id} {state}: "
                f"{status.get('StateChangeReason', 'unknown')}"
            )
        time.sleep(poll_interval)


def _fetch_results(athena_client, execution_id: str) -> pl.DataFrame:
    """Page through Athena results and return a DataFrame."""
    rows = []
    headers = None
    paginator = athena_client.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=execution_id):
        result_rows = page["ResultSet"]["Rows"]
        if headers is None:
            headers = [col["VarCharValue"] for col in result_rows[0]["Data"]]
            result_rows = result_rows[1:]
        for row in result_rows:
            rows.append([cell.get("VarCharValue", "") for cell in row["Data"]])
    return pl.DataFrame(rows, schema=headers, orient="row")


def run_sql_file(athena_client, filename: str) -> pl.DataFrame:
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    qid = _run_query(athena_client, sql, result_prefix=f"test/{filename}/")
    _wait(athena_client, qid)
    return _fetch_results(athena_client, qid)


def load_snapshot(csv_filename: str) -> pl.DataFrame:
    return pl.read_csv(DATA_DEV / csv_filename, infer_schema_length=0)


# ── list_price_increases.sql ──────────────────────────────────────────────────

class TestListPriceIncreasesAWS:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "scrape_date",
        "prev_list_price", "current_list_price", "price_increase",
        "pct_increase", "rank",
    }

    @pytest.fixture(scope="class")
    def result(self, athena):
        return run_sql_file(athena, "list_price_increases.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0, "Expected at least one row"

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert int(grp["rank"].max()) <= 5, f"{store}: rank exceeded 5"

    def test_sorted_by_store_then_rank(self, result):
        stores = result["store"].to_list()
        assert stores == sorted(stores)
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            ranks = [int(r) for r in grp["rank"].to_list()]
            assert ranks == list(range(1, len(grp) + 1))

    def test_snapshot_columns_match(self, result):
        snapshot = load_snapshot("list_price_increases.csv")
        assert set(snapshot.columns) == set(result.columns)

    def test_snapshot_stores_match(self, result):
        snapshot = load_snapshot("list_price_increases.csv")
        assert set(snapshot["store"].unique().to_list()) == set(result["store"].unique().to_list())


# ── list_price_decreases.sql ──────────────────────────────────────────────────

class TestListPriceDecreasesAWS:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "is_available", "store", "scrape_date",
        "prev_list_price", "current_list_price", "price_decrease",
        "pct_decrease", "rank",
    }

    @pytest.fixture(scope="class")
    def result(self, athena):
        return run_sql_file(athena, "list_price_decreases.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert int(grp["rank"].max()) <= 5, f"{store}: rank exceeded 5"

    def test_sorted_by_store_then_rank(self, result):
        stores = result["store"].to_list()
        assert stores == sorted(stores)
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            ranks = [int(r) for r in grp["rank"].to_list()]
            assert ranks == list(range(1, len(grp) + 1))

    def test_snapshot_columns_match(self, result):
        snapshot = load_snapshot("list_price_decreases.csv")
        assert set(snapshot.columns) == set(result.columns)

    def test_snapshot_stores_match(self, result):
        snapshot = load_snapshot("list_price_decreases.csv")
        assert set(snapshot["store"].unique().to_list()) == set(result["store"].unique().to_list())


# ── discounts.sql ─────────────────────────────────────────────────────────────

class TestDiscountsAWS:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "scrape_date",
        "prev_price", "current_price", "price_decrease", "pct_decrease", "rank",
    }

    @pytest.fixture(scope="class")
    def result(self, athena):
        return run_sql_file(athena, "discounts.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert int(grp["rank"].max()) <= 5, f"{store}: rank exceeded 5"

    def test_snapshot_columns_match(self, result):
        snapshot = load_snapshot("discounts.csv")
        assert set(snapshot.columns) == set(result.columns)

    def test_snapshot_stores_match(self, result):
        snapshot = load_snapshot("discounts.csv")
        assert set(snapshot["store"].unique().to_list()) == set(result["store"].unique().to_list())


# ── 30d_avg_deals.sql ────────────────────────────────────────────────────────

class TestBestDealsAWS:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "link", "image",
        "current_price", "avg_price_30d", "pct_discount", "rank",
    }

    @pytest.fixture(scope="class")
    def result(self, athena):
        return run_sql_file(athena, "30d_avg_deals.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert int(grp["rank"].max()) <= 5, f"{store}: rank exceeded 5"

    def test_snapshot_columns_match(self, result):
        snapshot = load_snapshot("avg_deals_30d.csv")
        assert set(snapshot.columns) == set(result.columns)

    def test_snapshot_stores_match(self, result):
        snapshot = load_snapshot("avg_deals_30d.csv")
        assert set(snapshot["store"].unique().to_list()) == set(result["store"].unique().to_list())


# ── price_changes table health check ─────────────────────────────────────────

class TestPriceChangesTableAWS:
    """Sanity checks on the price_changes table itself."""

    @pytest.fixture(scope="class")
    def result(self, athena):
        sql = "SELECT COUNT(*) AS cnt, COUNT(DISTINCT store) AS stores FROM price_changes"
        qid = _run_query(athena, sql, result_prefix="test/health/")
        _wait(athena, qid)
        return _fetch_results(athena, qid)

    def test_has_rows(self, result):
        assert int(result[0, "cnt"]) > 0

    def test_has_multiple_stores(self, result):
        assert int(result[0, "stores"]) >= 2
