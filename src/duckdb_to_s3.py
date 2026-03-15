import duckdb
import os

DUCKDB_FILE = "products.duckdb"
TABLE = "products"
S3_PATH = "s3://BDM060897/Products"

con = duckdb.connect(DUCKDB_FILE)

# Enable S3 access
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

# Export partitioned parquet directly to S3
con.execute(f"""
COPY (
    SELECT *
    FROM {TABLE}
)
TO '{S3_PATH}'
(
    FORMAT PARQUET,
    PARTITION_BY (date, store),
    OVERWRITE_OR_IGNORE TRUE
);
""")

print("Export complete")