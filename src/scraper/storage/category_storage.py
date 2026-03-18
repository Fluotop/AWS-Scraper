import os
import boto3
from abc import ABC, abstractmethod


class BaseCategoryStorage(ABC):
    """Storage abstraction for category DuckDB files."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    @abstractmethod
    def upload_local_db(self):
        """Upload the local DuckDB file to remote storage (if applicable)."""
        pass

class AWSCategoryStorage(BaseCategoryStorage):
    """S3-backed storage for category DuckDB files."""

    def __init__(self, db_path: str, bucket: str, prefix: str = "categories"):
        super().__init__(db_path)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.s3 = boto3.client("s3")

    def _key(self):
        return f"{self.prefix}/{os.path.basename(self.db_path)}"

    def upload_local_db(self):
        with open(self.db_path, "rb") as f:
            self.s3.put_object(Bucket=self.bucket, Key=self._key(), Body=f.read())
