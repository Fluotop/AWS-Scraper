"""Shared utilities for history Lambda functions.

On AWS this file lives in a Lambda layer at /opt/python/history_layer.py
so each history Lambda can do: from history_layer import ...
"""
import os
import time
import io
import polars as pl
import boto3

s3     = boto3.client("s3")
athena = boto3.client("athena")

BUCKET          = "bdm060897-prod"
DATABASE        = os.environ.get("DATABASE", "products_db")
OUTPUT_LOCATION = os.environ.get("OUTPUT_LOCATION", "s3://bdm060897-prod/")


def _wait(execution_id, poll_interval=1):
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


def run_athena(sql, result_prefix):
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": OUTPUT_LOCATION + result_prefix},
    )["QueryExecutionId"]
    _wait(qid)
    return qid


def delete_s3_prefix(prefix):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        objects = page.get("Contents", [])
        if objects:
            s3.delete_objects(
                Bucket=BUCKET,
                Delete={"Objects": [{"Key": o["Key"]} for o in objects]}
            )


def run_history(source_prefix, history_prefix):
    """Read product_id/store pairs from a previous query's CSV result,
    then fetch and save their full price history from the products table."""

    # Read the source CSV result from S3
    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=source_prefix)
    key = response["Contents"][0]["Key"]
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    df = pl.read_csv(io.BytesIO(obj["Body"].read()))

    # Build IN filter from product_id/store pairs
    product_filter = ", ".join(
        f"('{row[0]}', '{row[1]}')"
        for row in df.select(["product_id", "store"]).rows()
    )

    sql = f"""
        SELECT product_id, store, scrape_date, list_price, price
        FROM products
        WHERE (product_id, store) IN ({product_filter})
        ORDER BY product_id, store, scrape_date
    """
    delete_s3_prefix(history_prefix)
    run_athena(sql, history_prefix)
    return {"status": "succeeded", "output_prefix": history_prefix}
