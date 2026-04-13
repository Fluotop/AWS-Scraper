"""Shared fixtures and synthetic seed data for SQL query tests."""

import re
from datetime import date
from pathlib import Path

import duckdb
import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR   = REPO_ROOT / "terraform" / "lambda" / "sql"

# ── Dates ─────────────────────────────────────────────────────────────────────
PREV_DATE   = date(2026, 4, 6)   # second-to-last scrape date
LATEST_DATE = date(2026, 4, 7)   # latest scrape date
HIST_DATE   = date(2026, 3, 8)   # 30-day history date (within window for best deals)

# ── Synthetic products ────────────────────────────────────────────────────────
#
# Columns: product_id, store, name, brand, link, image, is_available,
#          scrape_date, list_price, price
#
# Design:
#   C1-C2  chedraui list_price increases
#   C3-C4  chedraui list_price decreases
#   C5-C6  chedraui price decreases (list unchanged)
#   C7     chedraui no change (excluded from price_changes)
#   S1-S2  superaki list_price increases
#   S3     superaki list + price decrease
#   D_C1-2 chedraui 30-day deal products (appear on HIST_DATE & LATEST_DATE)
#   D_S1   superaki 30-day deal product

def _products():
    rows = []

    def add_change(pid, store, name, prev_list, cur_list, prev_price, cur_price, brand="Brand"):
        """Product present on both PREV_DATE and LATEST_DATE."""
        for scrape_date, lp, p in [
            (PREV_DATE,   prev_list,  prev_price),
            (LATEST_DATE, cur_list,   cur_price),
        ]:
            rows.append((
                pid, store, name, brand,
                f"https://example.com/{pid}",
                f"https://img.example.com/{pid}.jpg",
                True, scrape_date, lp, p,
            ))

    def add_deal(pid, store, name, hist_price, cur_price, list_price=100.0, brand="Brand"):
        """Product present on HIST_DATE (historical avg) and LATEST_DATE only.
        Prices are identical on PREV_DATE-equivalent → NOT in price_changes."""
        for scrape_date, lp, p in [
            (HIST_DATE,   list_price, hist_price),
            (LATEST_DATE, list_price, cur_price),
        ]:
            rows.append((
                pid, store, name, brand,
                f"https://example.com/{pid}",
                f"https://img.example.com/{pid}.jpg",
                True, scrape_date, lp, p,
            ))

    # chedraui – list_price increases (ranked by pct_increase DESC)
    add_change("C1", "chedraui", "Prod C1", prev_list=100, cur_list=200, prev_price=90, cur_price=90)   # +100%
    add_change("C2", "chedraui", "Prod C2", prev_list=100, cur_list=180, prev_price=90, cur_price=90)   # +80%

    # chedraui – list_price decreases (ranked by pct_decrease DESC)
    add_change("C3", "chedraui", "Prod C3", prev_list=200, cur_list=100, prev_price=180, cur_price=180) # -50%
    add_change("C4", "chedraui", "Prod C4", prev_list=200, cur_list=120, prev_price=180, cur_price=180) # -40%

    # chedraui – price (sale) decreases (list unchanged)
    add_change("C5", "chedraui", "Prod C5", prev_list=100, cur_list=100, prev_price=100, cur_price=20)  # -80%
    add_change("C6", "chedraui", "Prod C6", prev_list=100, cur_list=100, prev_price=100, cur_price=40)  # -60%

    # chedraui – no change (should NOT appear in price_changes)
    add_change("C7", "chedraui", "Prod C7", prev_list=100, cur_list=100, prev_price=90, cur_price=90)

    # superaki – list_price increases
    add_change("S1", "superaki", "Prod S1", prev_list=100, cur_list=300, prev_price=90, cur_price=90)   # +200%
    add_change("S2", "superaki", "Prod S2", prev_list=100, cur_list=150, prev_price=90, cur_price=90)   # +50%

    # superaki – list + price decrease
    add_change("S3", "superaki", "Prod S3", prev_list=200, cur_list=100, prev_price=180, cur_price=90)  # list -50%, price -50%

    # 30-day deal products (appear on HIST_DATE and LATEST_DATE only)
    add_deal("D_C1", "chedraui", "Deal C1", hist_price=1000, cur_price=100, list_price=1000.0)  # 30d avg=1000, cur=100 → 90% off
    add_deal("D_C2", "chedraui", "Deal C2", hist_price=500,  cur_price=80,  list_price=500.0)   # 30d avg=500,  cur=80  → 84% off
    add_deal("D_S1", "superaki", "Deal S1", hist_price=1000, cur_price=100, list_price=1000.0)  # 30d avg=1000, cur=100 → 90% off

    return rows


# ── DuckDB price_changes SQL (Athena CTAS clauses removed) ────────────────────
SQL_PRICE_CHANGES_DUCKDB = """
CREATE TABLE price_changes AS
WITH last_two_dates AS (
    SELECT DISTINCT scrape_date FROM products ORDER BY scrape_date DESC LIMIT 2
),
filtered AS (
    SELECT product_id, store, name, brand, link, image, is_available,
           scrape_date, list_price, price
    FROM products
    WHERE scrape_date IN (SELECT scrape_date FROM last_two_dates)
),
with_lag AS (
    SELECT *,
        LAG(list_price) OVER (PARTITION BY product_id, store ORDER BY scrape_date) AS prev_list_price,
        LAG(price)      OVER (PARTITION BY product_id, store ORDER BY scrape_date) AS prev_price
    FROM filtered
)
SELECT *,
    list_price - prev_list_price                           AS list_price_diff,
    (list_price - prev_list_price) / prev_list_price * 100 AS list_price_pct_change,
    price - prev_price                                     AS price_diff,
    (price - prev_price) / prev_price * 100                AS price_pct_change
FROM with_lag
WHERE scrape_date = (SELECT MAX(scrape_date) FROM last_two_dates)
  AND is_available = TRUE
  AND prev_list_price > 0
  AND prev_price > 0
  AND (list_price - prev_list_price <> 0 OR price - prev_price <> 0);
"""


def adapt_sql_for_duckdb(sql: str) -> str:
    """Translate Athena/Trino-specific syntax to DuckDB equivalents."""
    # date_add('day', -N, col) → (col - INTERVAL 'N' DAY)
    sql = re.sub(
        r"date_add\('day',\s*-(\d+),\s*(\w+)\)",
        lambda m: f"({m.group(2)} - INTERVAL '{m.group(1)}' DAY)",
        sql,
    )
    # date_add('day', +N, col) → (col + INTERVAL 'N' DAY)
    sql = re.sub(
        r"date_add\('day',\s*\+?(\d+),\s*(\w+)\)",
        lambda m: f"({m.group(2)} + INTERVAL '{m.group(1)}' DAY)",
        sql,
    )
    return sql


def duck_to_polars(result) -> "pl.DataFrame":
    """Convert a DuckDB result to a Polars DataFrame without requiring pyarrow."""
    import polars as pl
    cols = [d[0] for d in result.description]
    rows = result.fetchall()
    if not rows:
        return pl.DataFrame({c: [] for c in cols})
    return pl.DataFrame(
        {c: [row[i] for row in rows] for i, c in enumerate(cols)}
    )


def load_sql(filename: str, dialect: str = "duckdb") -> str:
    """Read a SQL file from the terraform/lambda/sql directory."""
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    if dialect == "duckdb":
        sql = adapt_sql_for_duckdb(sql)
    return sql


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def duckdb_con():
    """In-memory DuckDB loaded with synthetic products and price_changes."""
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE products (
            product_id   VARCHAR,
            store        VARCHAR,
            name         VARCHAR,
            brand        VARCHAR,
            link         VARCHAR,
            image        VARCHAR,
            is_available BOOLEAN,
            scrape_date  DATE,
            list_price   DOUBLE,
            price        DOUBLE
        )
    """)
    con.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)",
        _products(),
    )
    con.execute("DROP TABLE IF EXISTS price_changes")
    con.execute(SQL_PRICE_CHANGES_DUCKDB)
    yield con
    con.close()


@pytest.fixture(scope="session")
def data_dev_dir():
    return Path(__file__).parent / "data_dev"
