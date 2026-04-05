import duckdb
import boto3
import os
import shutil

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUCKDB_FILE = os.path.join(WORKSPACE_DIR, "src", "products.duckdb")
TABLE = "products"

LOCAL_EXPORT = "export"
BUCKET = "bdm060897-prod"
PREFIX = "scraper/products"

# clean export folder
if os.path.exists(LOCAL_EXPORT):
    shutil.rmtree(LOCAL_EXPORT)

os.makedirs(LOCAL_EXPORT, exist_ok=True)

# connect duckdb
con = duckdb.connect(DUCKDB_FILE)

# export partitioned parquet locally
con.execute(f"""
COPY (
    SELECT
        CAST(product_id AS VARCHAR) AS product_id,
        store,
        scrape_date,
        name,
        brand,
        maincat,
        cat,
        subcat,
        catid,
        image,
        price,
        priceWithoutDiscount AS pricewithoutdiscount,
        list_price,
        is_available,
        link
    FROM {TABLE}
)
TO '{LOCAL_EXPORT}'
(
    FORMAT PARQUET,
    PARTITION_BY (scrape_date, store)
);
""")

print("DuckDB export complete")

# upload to S3
s3 = boto3.client("s3")

for root, dirs, files in os.walk(LOCAL_EXPORT):
    for file in files:

        local_path = os.path.join(root, file)

        rel_path = os.path.relpath(local_path, LOCAL_EXPORT)
        s3_key = f"{PREFIX}/{rel_path}".replace("\\", "/")

        print("Uploading:", s3_key)

        s3.upload_file(local_path, BUCKET, s3_key)

print("Upload complete")