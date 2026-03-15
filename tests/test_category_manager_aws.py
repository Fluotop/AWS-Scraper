import os
import tempfile
from pathlib import Path
import sys
import boto3
import duckdb
import pytest
from moto import mock_aws

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.Scraper.scrapers.category_manager import BaseCategoryManager


class DummyCategoryManager(BaseCategoryManager):
    """Simple test implementation that doesn't call any external APIs."""

    def create_session(self):
        pass

    def extract_category_data(self, data: dict) -> dict:
        return {}


@mock_aws
def test_category_manager_uploads_duckdb_to_s3():
    # Arrange
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    s3 = boto3.client("s3")
    bucket = "test-bucket"
    s3.create_bucket(Bucket=bucket)

    with tempfile.TemporaryDirectory() as tmpdir:
        categories_db = os.path.join(tmpdir, "categories.duckdb")

        manager = DummyCategoryManager(
            store_name="test",
            base_url="https://example.com",
            api_endpoint="https://example.com/api",
            categories_db=categories_db,
            storage_type="aws",
            aws_bucket=bucket,
            aws_prefix="categories",
        )

        # Create a dummy categories table and save it
        categories = {
            "cat1": {
                "name": "Category 1",
                "parent": None,
                "path": "/cat1/",
                "level": 1,
                "store": "test",
                "link": "https://example.com/cat1",
            }
        }

        manager.save_to_database(categories)

        # Assert local file exists
        assert os.path.exists(categories_db)

        # Assert object was uploaded to S3
        resp = s3.list_objects_v2(Bucket=bucket, Prefix="categories/")
        keys = [o["Key"] for o in resp.get("Contents", [])]
        assert len(keys) == 1
        assert keys[0].endswith("categories.duckdb")

        # Validate the uploaded DuckDB contains the categories table
        obj = s3.get_object(Bucket=bucket, Key=keys[0])
        data = obj["Body"].read()

        # Write to a new temporary file and verify using duckdb
        downloaded_path = os.path.join(tmpdir, "downloaded.duckdb")
        with open(downloaded_path, "wb") as f:
            f.write(data)

        conn = duckdb.connect(downloaded_path)
        rows = conn.execute("SELECT id, name FROM categories").fetchall()
        assert rows == [("cat1", "Category 1")]
        conn.close()
