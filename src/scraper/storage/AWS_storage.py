import polars as pl
import boto3
from scraper.storage.base_storage import BaseStorage
from datetime import date
import io

print("LOADING aws_STORAGE FROM:", __file__)


class AWSStorage(BaseStorage):

    STRING_COLUMNS = [
        "product_id", "store", "name", "brand", "maincat", "cat",
        "subcat", "catid", "image", "link"
    ]

    def __init__(self, bucket, prefix="store_scraper"):
        self.bucket = bucket
        self.prefix = prefix
        self.s3 = boto3.client("s3")

    def create_products_table(self):
        pass

    def insert_products(self, products_data):

        if not products_data:
            return

        columns = [
            "product_id", "store", "scrape_date", "name", "brand",
            "maincat", "cat", "subcat", "catid",
            "image", "price", "pricewithoutdiscount",
            "list_price", "is_available", "link"
        ]

        df = pl.DataFrame(products_data, schema=columns, orient="row")

        df = df.with_columns(
            pl.col(self.STRING_COLUMNS).cast(pl.Utf8, strict=False),
            pl.col("scrape_date").cast(pl.Date),
            pl.col("is_available").cast(pl.Boolean, strict=False),
        )

        store = df["store"][0]

        key = (
            f"{self.prefix}/"
            f"scrape_date={date.today()}/"
            f"store={store}/"
            f"products.parquet"
        )

        buf = io.BytesIO()
        df.write_parquet(buf)
        buf.seek(0)

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=buf.getvalue()
        )