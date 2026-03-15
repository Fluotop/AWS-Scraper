import io
import os
import sys
from datetime import date

import boto3
import polars as pl
import pytest
from moto import mock_aws

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.Scraper.storage.AWS_storage import AWSStorage



@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@mock_aws
def test_aws_storage_parquet_write_and_overwrite(aws_credentials):
    s3 = boto3.client("s3")

    bucket_name = "test-bucket"
    s3.create_bucket(Bucket=bucket_name)

    storage = AWSStorage(bucket=bucket_name, prefix="testprefix")

    today = date.today()
    record1 = [
        (
            "p1","MyStore",today,"Name1","Brand1",
            "maincat","cat","subcat","catid","img",
            1.0,0.9,1.0,True,"link1"
        ),
        (
            "p2","MyStore",today,"Name2","Brand2",
            "maincat","cat","subcat","catid","img",
            1.0,0.9,1.0,True,"link2"
        )
    ]

    # Write first parquet file
    storage.insert_products(record1)

    # Validate the S3 path structure
    resp = s3.list_objects_v2(Bucket=bucket_name, Prefix="testprefix/")
    keys = []
    for o in resp.get("Contents", []):
        keys.append(o["Key"])
    assert len(keys) == 1
    key = keys[0]
    assert key.startswith("testprefix/")
    assert f"scrape_date={today}" in key
    assert "store=MyStore" in key
    assert key.endswith("products.parquet")

    # Validate parquet format and content
    obj = s3.get_object(Bucket=bucket_name, Key=key)
    assert obj["ContentLength"] > 0
    df = pl.read_parquet(io.BytesIO(obj["Body"].read()))
    assert df.shape[0] == 2
    assert df["product_id"][0] == "p1"
    assert df["name"][0] == "Name1"

    # Overwrite with a new row and ensure only one file exists
    record2 = [
        (
            "p3","MyStore",today,"Name3","Brand3",
            "maincat","cat","subcat","catid","img",
            1.0,0.9,1.0,True,"link3"
        ),
        (
            "p4","MyStore",today,"Name4","Brand4",
            "maincat","cat","subcat","catid","img",
            1.0,0.9,1.0,True,"link4"
        )
    ]
    storage.insert_products(record2)

    resp2 = s3.list_objects_v2(Bucket=bucket_name, Prefix="testprefix/")
    keys2 = [o["Key"] for o in resp2.get("Contents", [])]
    assert len(keys2) == 1
    assert keys2[0] == key

    obj2 = s3.get_object(Bucket=bucket_name, Key=key)
    df2 = pl.read_parquet(io.BytesIO(obj2["Body"].read()))
    assert df2.shape[0] == 2
    assert df2["product_id"][0] == "p3"
    assert df2["name"][0] == "Name3"
