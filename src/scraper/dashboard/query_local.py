import re
import duckdb
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
DB_PATH = str(_HERE / "../../products.duckdb")
SQL_DIR = _HERE / "../../../terraform/lambda/sql"
OUT_DIR = _HERE / "../sql_results"

def adapt_sql_for_duckdb(sql: str) -> str:
    """Translate Athena/Trino-specific syntax to DuckDB equivalents."""
    sql = re.sub(
        r"date_add\('day',\s*-(\d+),\s*(\w+)\)",
        lambda m: f"({m.group(2)} - INTERVAL '{m.group(1)}' DAY)",
        sql,
    )
    sql = re.sub(
        r"date_add\('day',\s*\+?(\d+),\s*(\w+)\)",
        lambda m: f"({m.group(2)} + INTERVAL '{m.group(1)}' DAY)",
        sql,
    )
    return sql


def load_sql(filename: str) -> str:
    return adapt_sql_for_duckdb((SQL_DIR / filename).read_text(encoding="utf-8").rstrip().rstrip(";"))


# ── run SQL files and write CSVs ──────────────────────────────────────────────
def run_queries():
    con = duckdb.connect(DB_PATH)

    con.execute("DROP TABLE IF EXISTS price_changes;")

    con.execute("""
CREATE TABLE price_changes AS
WITH last_two_dates AS (
    SELECT scrape_date
    FROM products
    GROUP BY scrape_date
    ORDER BY scrape_date DESC
    LIMIT 2
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
    """)

    def write_csv(sql: str, path: Path) -> None:
        con.execute(f"COPY ({sql}) TO '{path.as_posix()}' (FORMAT CSV, HEADER)")

    def get_history_sql(sql: str) -> str:
        rows = con.execute(f"SELECT DISTINCT product_id, store FROM ({sql})").fetchall()
        if not rows:
            return "SELECT NULL::VARCHAR AS product_id, NULL::VARCHAR AS store, NULL::DATE AS scrape_date, NULL::DOUBLE AS list_price, NULL::DOUBLE AS price WHERE FALSE"
        product_filter = ", ".join(f"('{r[0]}', '{r[1]}')" for r in rows)
        return f"""
        SELECT product_id, store, scrape_date, list_price, price
        FROM products
        WHERE (product_id, store) IN ({product_filter})
        ORDER BY product_id, store, scrape_date
        """

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sql_list_increase  = load_sql("list_price_increases.sql")
    sql_list_decrease  = load_sql("list_price_decreases.sql")
    sql_price_decrease = load_sql("discounts.sql")
    sql_avg_deals_30d  = load_sql("avg_deals_30d.sql")

    write_csv(sql_list_increase,  OUT_DIR / "list_price_increases.csv")
    write_csv(sql_list_decrease,  OUT_DIR / "list_price_decreases.csv")
    write_csv(sql_price_decrease, OUT_DIR / "discounts.csv")
    write_csv(sql_avg_deals_30d,  OUT_DIR / "30d_avg_deals.csv")

    write_csv(get_history_sql(sql_list_increase),  OUT_DIR / "list_price_increases_history.csv")
    write_csv(get_history_sql(sql_list_decrease),  OUT_DIR / "list_price_decreases_history.csv")
    write_csv(get_history_sql(sql_price_decrease), OUT_DIR / "discounts_history.csv")
    write_csv(get_history_sql(sql_avg_deals_30d),  OUT_DIR / "avg_deals_30d_history.csv")

