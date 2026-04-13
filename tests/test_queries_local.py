"""Local DuckDB tests for the 4 Athena SQL query files.

Uses an in-memory DuckDB seeded with controlled synthetic data so that
every assertion is against known, deterministic values.

Run:  pytest tests/test_queries_local.py -v
"""

import polars as pl
import pytest
from conftest import load_sql, duck_to_polars, LATEST_DATE


# ── helpers ───────────────────────────────────────────────────────────────────

def run(con, filename) -> pl.DataFrame:
    sql = load_sql(filename, dialect="duckdb")
    return duck_to_polars(con.execute(sql))


# ── price_changes table (prerequisite) ───────────────────────────────────────

class TestPriceChangesTable:
    """Validate that the price_changes intermediate table is built correctly."""

    def test_only_latest_date(self, duckdb_con):
        df = duck_to_polars(duckdb_con.execute(
            "SELECT DISTINCT scrape_date FROM price_changes"
        ))
        dates = df["scrape_date"].to_list()
        assert all(d == LATEST_DATE for d in dates)

    def test_excludes_no_change_product(self, duckdb_con):
        ids = duck_to_polars(duckdb_con.execute(
            "SELECT product_id FROM price_changes"
        ))["product_id"].to_list()
        assert "C7" not in ids, "C7 has no price change and must be excluded"

    def test_excludes_unavailable_products(self, duckdb_con):
        # All rows must have is_available = True (enforced by the WHERE clause)
        unavailable = duck_to_polars(duckdb_con.execute(
            "SELECT COUNT(*) FROM price_changes WHERE is_available = FALSE"
        ))[0, 0]
        assert unavailable == 0

    def test_prev_prices_populated(self, duckdb_con):
        nulls = duck_to_polars(duckdb_con.execute(
            "SELECT COUNT(*) FROM price_changes WHERE prev_list_price IS NULL OR prev_price IS NULL"
        ))[0, 0]
        assert nulls == 0

    def test_known_products_present(self, duckdb_con):
        ids = set(duck_to_polars(duckdb_con.execute(
            "SELECT product_id FROM price_changes"
        ))["product_id"].to_list())
        # products with known price changes
        for pid in ("C1", "C2", "C3", "C4", "C5", "C6", "S1", "S2", "S3"):
            assert pid in ids, f"{pid} should be in price_changes"


# ── list_price_increases.sql ──────────────────────────────────────────────────

class TestListPriceIncreases:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "scrape_date",
        "prev_list_price", "current_list_price", "price_increase",
        "pct_increase", "rank",
    }

    def test_columns(self, duckdb_con):
        df = run(duckdb_con, "list_price_increases.sql")
        assert self.EXPECTED_COLS == set(df.columns)

    def test_max_rank_per_store(self, duckdb_con):
        df = run(duckdb_con, "list_price_increases.sql")
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 5, f"{store}: rank exceeded 5"

    def test_sorted_by_store_then_rank(self, duckdb_con):
        df = run(duckdb_con, "list_price_increases.sql")
        stores = df["store"].to_list()
        assert stores == sorted(stores)
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].to_list() == list(range(1, len(grp) + 1))

    def test_chedraui_rank1_is_highest_pct(self, duckdb_con):
        df = run(duckdb_con, "list_price_increases.sql")
        chedraui = df.filter(pl.col("store") == "chedraui").sort("rank")
        # C1: +100%, C2: +80%
        assert chedraui[0, "product_id"] == "C1"
        assert chedraui[0, "pct_increase"] == pytest.approx(100.0, rel=1e-2)

    def test_superaki_rank1_is_highest_pct(self, duckdb_con):
        df = run(duckdb_con, "list_price_increases.sql")
        superaki = df.filter(pl.col("store") == "superaki").sort("rank")
        # S1: +200%, S2: +50%
        assert superaki[0, "product_id"] == "S1"
        assert superaki[0, "pct_increase"] == pytest.approx(200.0, rel=1e-2)

    def test_only_increases_returned(self, duckdb_con):
        df = run(duckdb_con, "list_price_increases.sql")
        assert (df["current_list_price"] > df["prev_list_price"]).all()


# ── list_price_decreases.sql ──────────────────────────────────────────────────

class TestListPriceDecreases:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "is_available", "store", "scrape_date",
        "prev_list_price", "current_list_price", "price_decrease",
        "pct_decrease", "rank",
    }

    def test_columns(self, duckdb_con):
        df = run(duckdb_con, "list_price_decreases.sql")
        assert self.EXPECTED_COLS == set(df.columns)

    def test_max_rank_per_store(self, duckdb_con):
        df = run(duckdb_con, "list_price_decreases.sql")
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 5, f"{store}: rank exceeded 5"

    def test_sorted_by_store_then_rank(self, duckdb_con):
        df = run(duckdb_con, "list_price_decreases.sql")
        stores = df["store"].to_list()
        assert stores == sorted(stores)
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].to_list() == list(range(1, len(grp) + 1))

    def test_chedraui_rank1_is_largest_pct_drop(self, duckdb_con):
        df = run(duckdb_con, "list_price_decreases.sql")
        chedraui = df.filter(pl.col("store") == "chedraui").sort("rank")
        # C3: -50% > C4: -40%
        assert chedraui[0, "product_id"] == "C3"
        assert chedraui[0, "pct_decrease"] == pytest.approx(50.0, rel=1e-2)

    def test_superaki_rank1(self, duckdb_con):
        df = run(duckdb_con, "list_price_decreases.sql")
        superaki = df.filter(pl.col("store") == "superaki").sort("rank")
        assert superaki[0, "product_id"] == "S3"

    def test_only_decreases_returned(self, duckdb_con):
        df = run(duckdb_con, "list_price_decreases.sql")
        assert (df["current_list_price"] < df["prev_list_price"]).all()

    def test_price_decrease_values_positive(self, duckdb_con):
        df = run(duckdb_con, "list_price_decreases.sql")
        assert (df["price_decrease"] > 0).all()


# ── discounts.sql (sale price decreases) ─────────────────────────────────────

class TestDiscounts:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "scrape_date",
        "prev_price", "current_price", "price_decrease", "pct_decrease", "rank",
    }

    def test_columns(self, duckdb_con):
        df = run(duckdb_con, "discounts.sql")
        assert self.EXPECTED_COLS == set(df.columns)

    def test_max_rank_per_store(self, duckdb_con):
        df = run(duckdb_con, "discounts.sql")
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 5, f"{store}: rank exceeded 5"

    def test_sorted_by_store_then_rank(self, duckdb_con):
        df = run(duckdb_con, "discounts.sql")
        stores = df["store"].to_list()
        assert stores == sorted(stores)
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].to_list() == list(range(1, len(grp) + 1))

    def test_chedraui_rank1_is_largest_pct_drop(self, duckdb_con):
        df = run(duckdb_con, "discounts.sql")
        chedraui = df.filter(pl.col("store") == "chedraui").sort("rank")
        # C5: -80%, C6: -60%
        assert chedraui[0, "product_id"] == "C5"
        assert chedraui[0, "pct_decrease"] == pytest.approx(80.0, rel=1e-2)

    def test_superaki_rank1(self, duckdb_con):
        df = run(duckdb_con, "discounts.sql")
        superaki = df.filter(pl.col("store") == "superaki").sort("rank")
        # S3: price -50%
        assert superaki[0, "product_id"] == "S3"
        assert superaki[0, "pct_decrease"] == pytest.approx(50.0, rel=1e-2)

    def test_only_price_decreases_returned(self, duckdb_con):
        df = run(duckdb_con, "discounts.sql")
        assert (df["current_price"] < df["prev_price"]).all()


# ── 30d_avg_deals.sql ────────────────────────────────────────────────────────

class TestBestDeals:
    EXPECTED_COLS = {
        "name", "product_id", "brand", "store", "link", "image",
        "current_price", "avg_price_30d", "pct_discount", "rank",
    }

    def test_columns(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        assert self.EXPECTED_COLS == set(df.columns)

    def test_max_rank_per_store(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].max() <= 5, f"{store}: rank exceeded 5"

    def test_sorted_by_store_then_rank(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        stores = df["store"].to_list()
        assert stores == sorted(stores)
        for store in df["store"].unique().to_list():
            grp = df.filter(pl.col("store") == store)
            assert grp["rank"].to_list() == list(range(1, len(grp) + 1))

    def test_chedraui_rank1_best_discount(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        chedraui = df.filter(pl.col("store") == "chedraui").sort("rank")
        # D_C1: 90% (1000→100) > D_C2: 84% (500→80) > C5: 80% (100→20)
        assert chedraui[0, "product_id"] == "D_C1"
        assert chedraui[0, "pct_discount"] == pytest.approx(90.0, rel=1e-2)

    def test_superaki_rank1_best_discount(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        superaki = df.filter(pl.col("store") == "superaki").sort("rank")
        # D_S1: 90% (1000→100) > S3: 50% (180→90)
        assert superaki[0, "product_id"] == "D_S1"
        assert superaki[0, "pct_discount"] == pytest.approx(90.0, rel=1e-2)

    def test_current_price_below_avg(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        assert (df["current_price"] < df["avg_price_30d"]).all()

    def test_discount_values_positive(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        assert (df["pct_discount"] > 0).all()

    def test_excludes_no_change_products(self, duckdb_con):
        df = run(duckdb_con, "30d_avg_deals.sql")
        ids = set(df["product_id"].to_list())
        # Price-change products use a different date pattern,
        # so they have no 30d history — they should not dominate deals
        assert "C7" not in ids, "C7 has no 30d history below current price"
