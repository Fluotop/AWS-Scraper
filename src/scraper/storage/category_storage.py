import os
import boto3
from abc import ABC, abstractmethod


class BaseCategoryStorage(ABC):
    """Storage abstraction for category DuckDB files."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    @abstractmethod
    def ensure_local_db(self):
        """Ensure the local DuckDB file exists (e.g., download from remote)."""
        pass

    @abstractmethod
    def upload_local_db(self):
        """Upload the local DuckDB file to remote storage (if applicable)."""
        pass


class LocalCategoryStorage(BaseCategoryStorage):
    """Local-only storage (no-op sync)."""

    def ensure_local_db(self):
        # Nothing required for local storage; the file is written/used locally.
        return

    def upload_local_db(self):
        # No remote storage to sync to.
        return


class AWSCategoryStorage(BaseCategoryStorage):
    """S3-backed storage for category DuckDB files."""

    def __init__(self, db_path: str, bucket: str, prefix: str = "categories"):
        super().__init__(db_path)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.s3 = boto3.client("s3")

    def _key(self):
        return f"{self.prefix}/{os.path.basename(self.db_path)}"

    def ensure_local_db(self):
        # Ensure destination directory exists
        local_dir = os.path.dirname(self.db_path)
        if local_dir:
            os.makedirs(local_dir, exist_ok=True)

        try:
            with open(self.db_path, "wb") as f:
                self.s3.download_fileobj(self.bucket, self._key(), f)
        except Exception as e:
            # If object doesn't exist yet, that is acceptable (will be created later).
            print(f"Warning: could not download categories DB from S3 ({self.bucket}/{self._key()}): {e}")

    def upload_local_db(self):
        with open(self.db_path, "rb") as f:
            self.s3.put_object(Bucket=self.bucket, Key=self._key(), Body=f.read())
