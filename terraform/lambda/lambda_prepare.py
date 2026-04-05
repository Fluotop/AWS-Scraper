import boto3
import os
import time

s3              = boto3.client("s3")
athena          = boto3.client("athena")
DATABASE        = os.environ.get("DATABASE", "products.db")
OUTPUT_LOCATION = os.environ.get("OUTPUT_LOCATION", "s3://bdm060897-prod/scraper/athena-results/")


def delete_s3_prefix(bucket, prefix):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if objects:
            s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": o["Key"]} for o in objects]}
            )
            
            
def _run_query(sql, prefix = "tmp/"):
    return athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": OUTPUT_LOCATION + prefix},
    )["QueryExecutionId"]
    
#TODO: how to see exception on aws?
def _wait(execution_id, poll_interval = 1):
    while True:
        status = athena.get_query_execution(QueryExecutionId=execution_id)[
            "QueryExecution"
        ]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            return
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(
                f"Athena query {execution_id} {state}: "
                f"{status.get('StateChangeReason', 'unknown')}"
            )
        time.sleep(poll_interval)


def run(sql, result_prefix = "tmp/"):
    qid = _run_query(sql, result_prefix)
    _wait(qid)
    return qid

# ── SQL ───────────────────────────────────────────────────────────────────────
SQL_DROP_PRICE_CHANGES = "DROP TABLE IF EXISTS price_changes;"

SQL_CREATE_PRICE_CHANGES = """
CREATE TABLE price_changes
WITH (
    external_location = 's3://bdm060897-prod/scraper/athena-results/price_changes/',
    format   = 'PARQUET'
)
AS
WITH last_two_dates AS (
    SELECT DISTINCT scrape_date
    FROM products
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
"""

def lambda_handler(event, context):
    print("Rebuilding price_changes …")
    run("MSCK REPAIR TABLE products;")
    run(SQL_DROP_PRICE_CHANGES)
    delete_s3_prefix("bdm060897-prod", "scraper/athena-results/price_changes/")
    run(SQL_CREATE_PRICE_CHANGES)
    delete_s3_prefix("bdm060897-prod", "scraper/athena-results/list_price_increases/")
    delete_s3_prefix("bdm060897-prod", "scraper/athena-results/list_price_decreases/")
    delete_s3_prefix("bdm060897-prod", "scraper/athena-results/discounts/")
    delete_s3_prefix("bdm060897-prod", "scraper/athena-results/avg_deals_30d/")
    return {"status": "ready"}
