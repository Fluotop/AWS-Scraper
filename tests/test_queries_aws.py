"""AWS Athena tests using moto to mock all AWS services.

No real credentials are needed. The moto mock handles all boto3 calls.
SQL correctness is validated by running the same .sql files through DuckDB
(same synthetic data as test_queries_local.py), since moto's Athena does not
execute real queries. TestAthenaInfrastructure verifies the boto3 API paths.

Run:  pytest tests/test_queries_aws.py -v
"""

import os
from pathlib import Path

import boto3
import polars as pl
import pytest
from moto import mock_aws

from conftest import SQL_DIR, load_sql, duck_to_polars

AWS_REGION      = "us-east-1"
BUCKET          = "test-scraper-bucket"
DATABASE        = "scraper"
OUTPUT_LOCATION = f"s3://{BUCKET}/athena-results/"

DATA_DEV = Path(__file__).parent / "data_dev"


# ── moto setup ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def aws_credentials():
    """Inject dummy credentials so moto intercepts all boto3 calls."""
    os.environ["AWS_ACCESS_KEY_ID"]     = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"]    = "testing"
    os.environ["AWS_SESSION_TOKEN"]     = "testing"
    os.environ["AWS_DEFAULT_REGION"]    = AWS_REGION


@pytest.fixture(scope="session")
def mock_ctx(aws_credentials):
    """Start the moto mock context for the entire test session."""
    with mock_aws():
        yield


@pytest.fixture(scope="session")
def s3(mock_ctx):
    client = boto3.client("s3", region_name=AWS_REGION)
    client.create_bucket(Bucket=BUCKET)
    return client


@pytest.fixture(scope="session")
def athena(mock_ctx, s3):
    """Mocked Athena client (s3 fixture ensures the result bucket exists)."""
    return boto3.client("athena", region_name=AWS_REGION)


# ── helpers ───────────────────────────────────────────────────────────────────

def run(duckdb_con, filename) -> pl.DataFrame:
    """Execute a SQL file against the DuckDB in-memory fixture."""
    sql = load_sql(filename, dialect="duckdb")
    return duck_to_polars(duckdb_con.execute(sql))


def load_snapshot(csv_filename: str) -> pl.DataFrame:
    return pl.read_csv(DATA_DEV / csv_filename, infer_schema_length=0)


# ── Athena infrastructure tests ───────────────────────────────────────────────

class TestAthenaInfrastructure:
    """Verify the mocked Athena and S3 clients behave correctly."""

    def test_list_work_groups(self, athena):
        resp = athena.list_work_groups()
        assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_start_query_execution(self, athena):
        resp = athena.start_query_execution(
            QueryString="SELECT 1",
            QueryExecutionContext={"Database": DATABASE},
            ResultConfiguration={"OutputLocation": OUTPUT_LOCATION},
        )
        assert "QueryExecutionId" in resp

    def test_get_query_execution_returns_state(self, athena):
        qid = athena.start_query_execution(
            QueryString="SELECT 1",
            QueryExecutionContext={"Database": DATABASE},
            ResultConfiguration={"OutputLocation": OUTPUT_LOCATION},
        )["QueryExecutionId"]
        state = athena.get_query_execution(
            QueryExecutionId=qid
        )["QueryExecution"]["Status"]["State"]
        assert state in ("QUEUED", "RUNNING", "SUCCEEDED")

    def test_s3_bucket_accessible(self, s3):
        buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
        assert BUCKET in buckets

    def test_s3_put_and_get(self, s3):
        s3.put_object(Bucket=BUCKET, Key="test/ping.txt", Body=b"ok")
        body = s3.get_object(Bucket=BUCKET, Key="test/ping.txt")["Body"].read()
        assert body == b"ok"


# ── list_price_increases.sql ──────────────────────────────────────────────────

class TestListPriceIncreasesAWS:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "scrape_date",
        "prev_list_price", "current_list_price", "price_increase",
        "pct_increase", "rank",
    }

    @pytest.fixture(scope="class")
    def result(self, duckdb_con):
        return run(duckdb_con, "list_price_increases.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 20, f"{store}: rank exceeded 20"

    def test_sorted_by_store_then_rank(self, result):
        stores = result["store"].to_list()
        assert stores == sorted(stores)
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert grp["rank"].to_list() == list(range(1, len(grp) + 1))

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
    def result(self, duckdb_con):
        return run(duckdb_con, "list_price_decreases.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 20, f"{store}: rank exceeded 20"

    def test_sorted_by_store_then_rank(self, result):
        stores = result["store"].to_list()
        assert stores == sorted(stores)
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert grp["rank"].to_list() == list(range(1, len(grp) + 1))

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
    def result(self, duckdb_con):
        return run(duckdb_con, "discounts.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 20, f"{store}: rank exceeded 20"

    def test_snapshot_columns_match(self, result):
        snapshot = load_snapshot("discounts.csv")
        assert set(snapshot.columns) == set(result.columns)

    def test_snapshot_stores_match(self, result):
        snapshot = load_snapshot("discounts.csv")
        assert set(snapshot["store"].unique().to_list()) == set(result["store"].unique().to_list())


# ── avg_deals_30d.sql ─────────────────────────────────────────────────────────

class TestBestDealsAWS:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "link", "image",
        "current_price", "avg_price_30d", "pct_discount", "rank",
    }

    @pytest.fixture(scope="class")
    def result(self, duckdb_con):
        return run(duckdb_con, "avg_deals_30d.sql")

    def test_columns(self, result):
        assert self.EXPECTED_COLS == set(result.columns)

    def test_returns_rows(self, result):
        assert len(result) > 0

    def test_max_rank_per_store(self, result):
        for store in result["store"].unique().to_list():
            grp = result.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 20, f"{store}: rank exceeded 20"

    def test_snapshot_columns_match(self, result):
        snapshot = load_snapshot("avg_deals_30d.csv")
        assert set(snapshot.columns) == set(result.columns)

    def test_snapshot_stores_match(self, result):
        snapshot = load_snapshot("avg_deals_30d.csv")
        assert set(snapshot["store"].unique().to_list()) == set(result["store"].unique().to_list())

