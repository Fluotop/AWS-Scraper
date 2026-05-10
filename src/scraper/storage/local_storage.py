import threading
import duckdb
from scraper.storage.base_storage import BaseStorage


class LocalStorage(BaseStorage):

    def __init__(self, db_path="products.duckdb"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = duckdb.connect(self.db_path)

    def create_products_table(self):

        with self._lock:
            self._conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT,
                store TEXT,
                scrape_date DATE,
                name TEXT,
                brand TEXT,
                maincat TEXT,
                cat TEXT,
                subcat TEXT,
                catid TEXT,
                image TEXT,
                price DOUBLE,
                pricewithoutdiscount DOUBLE,
                list_price DOUBLE,
                is_available BOOLEAN,
                link TEXT,
                PRIMARY KEY (product_id, store, scrape_date)
            )
            """)

    def insert_products(self, products_data, maincat_id=None):

        if not products_data:
            return

        with self._lock:
            self._conn.executemany("""
            INSERT OR REPLACE INTO products
            (product_id, store, scrape_date, name, brand, maincat,
             cat, subcat, catid, image, price, pricewithoutdiscount,
             list_price, is_available, link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, products_data)