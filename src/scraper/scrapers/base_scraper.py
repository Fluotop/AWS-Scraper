import time
import duckdb
import random
from abc import ABC, abstractmethod

from scraper.storage.local_storage import LocalStorage
from scraper.storage.AWS_storage import AWSStorage
from scraper.storage.category_storage import (
    BaseCategoryStorage,
    AWSCategoryStorage,
)

# --------------------------------------------------
# BASE SCRAPER CLASS - Common functionality
# --------------------------------------------------
class BaseScraper(ABC):
    """Base class for store scrapers with common functionality."""
    
    # Default constants - can be overridden in subclasses
    BASE_DELAY = 1.5
    PAGE_SIZE = 20
    MAX_RETRIES = 3
    BASE_URL = None  # Must be set by subclass
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    
    def __init__(
        self,
        store_name: str,
        storage=None,
        products_db: str = "products.duckdb",
        categories_db: str = "categories.duckdb",
        category_storage: BaseCategoryStorage = None,
        storage_type: str = "aws",
        aws_bucket: str = "bdm060897-prod",
        aws_prefix: str = "scraper/products",
    ):
        """Initialize the scraper.

        Args:
            store_name: Name of the store (used for database operations)
            storage: Optional storage backend instance. If passed as a string, it is treated as `products_db`.
            products_db: Path to local DuckDB products database (used when storage is local).
            categories_db: Path to categories database.
            category_storage: Optional category storage backend to use.
            storage_type: "local" or "aws" (used when `storage` is not provided).
            aws_bucket: S3 bucket name (required when storage_type == "aws").
            aws_prefix: S3 prefix (folder) for AWS parquet files.
        """
        self.store_name = store_name

        # Backwards compatibility: if storage is passed as a string, treat it as products_db
        if isinstance(storage, str):
            products_db = storage
            storage = None

        if storage is None:
            if storage_type == "aws":
                if not aws_bucket:
                    raise ValueError("aws_bucket is required when storage_type='aws'")
                storage = AWSStorage(bucket=aws_bucket, prefix=aws_prefix)
            else:
                storage = LocalStorage(db_path=products_db)

        self.storage = storage
        self.products_db = products_db
        self.categories_db = categories_db
        self.session = None

        if category_storage is not None:
            self.category_storage = category_storage
        else:
            if storage_type == "aws":
                if not aws_bucket:
                    raise ValueError("aws_bucket is required when storage_type='aws'")
                self.category_storage = AWSCategoryStorage(
                    db_path=self.categories_db,
                    bucket=aws_bucket,
                    prefix=aws_prefix,
                )
    
    # --------------------------------------------------
    # POLITE SLEEP (with jitter)
    # --------------------------------------------------
    def polite_sleep(self):
        """Sleep with random jitter to be polite to the server."""
        delay = self.BASE_DELAY + random.uniform(0.5, 1.5)
        time.sleep(delay)
    
    # --------------------------------------------------
    # SAFE REQUEST WITH RETRIES + BACKOFF
    # --------------------------------------------------
    def safe_get(self, url: str, params: dict):
        """
        Perform a GET request with retries and exponential backoff.
        
        Args:
            url: The URL to request
            params: Query parameters
            
        Returns:
            Response object if successful, None on 500 error, raises Exception on max retries exceeded
        """
        for attempt in range(self.MAX_RETRIES):
            response = self.session.get(url, headers=self.HEADERS, params=params, timeout=10)
            
            if response.status_code in (200, 206):
                return response
            
            # If the server returns 500, skip this response and let caller continue
            if response.status_code == 500:
                return None
            
            if response.status_code == 429:
                wait_time = 5 * (attempt + 1)
                print(f"Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            print(f"Error {response.status_code}. Retrying...")
            time.sleep(2)
        
        raise Exception("Max retries exceeded")
    
    # --------------------------------------------------
    # DATABASE OPERATIONS
    # --------------------------------------------------
    def create_products_table(self):
        """Create the products table via the configured storage backend."""
        self.storage.create_products_table()
    
    def insert_products(self, products_data: list):
        """Insert products via the configured storage backend."""
        self.storage.insert_products(products_data)

    def get_paths(self, category_filter=None, start_from=None):
        """
        Get category paths from the database.
        
        Args:
            category_filter: Optional dict with column:value filters (e.g., {"name": "Supermercado", "level": "1"})
            start_from: Optional path to start from (skips earlier paths)
            
        Returns:
            List of paths to scrape
        """

        conn = duckdb.connect(self.categories_db)
        cursor = conn.cursor()
        
        # Default query for level 3 categories
        query = "SELECT path FROM categories WHERE level = 3 AND store = ? ORDER BY path"
        params = [self.store_name]
        
        # If category_filter provided, modify query
        if category_filter:
            where_clauses = ["store = ?"]
            for key, value in category_filter.items():
                where_clauses.append(f"{key} = ?")
                params.append(value)
            
            # Get the parent category ID
            filter_query = f"SELECT id FROM categories WHERE {' AND '.join(where_clauses[:2])}"
            filter_params = params[:2]
            cursor.execute(filter_query, filter_params)
            row = cursor.fetchone()
            
            if row:
                parent_id = row[0]
                query = f"SELECT path FROM categories WHERE path LIKE ? AND level = 3 AND store = ? ORDER BY path"
                params = [f"/{parent_id}/%", self.store_name]
        
        cursor.execute(query, params)
        categories_to_scrape = cursor.fetchall()
        paths = [path[0] for path in categories_to_scrape]
        conn.close()
        
        # If start_from is provided, find its index and slice the paths list
        if start_from and start_from in paths:
            start_index = paths.index(start_from)
            paths = paths[start_index:]
        
        print(f"Found {len(paths)} paths to scrape")
        return paths
    
    # --------------------------------------------------
    # ABSTRACT METHODS - Must be implemented by subclasses
    # --------------------------------------------------
    @abstractmethod
    def create_session(self):
        """
        Create and configure a requests session for the store.
        Must set self.session.
        """
        pass
    
    @abstractmethod
    def scrape_category(self, path: str):
        """
        Scrape products from a single category.
        Must return a list of tuples with product data.
        
        Args:
            path: Category path to scrape
            
        Returns:
            List of tuples with product data
        """
        pass
    
    # --------------------------------------------------
    # MAIN SCRAPING FLOW
    # --------------------------------------------------
    def run(self, category_filter=None, start_from=None):
        """
        Run the scraper for all categories.
        
        Args:
            category_filter: Optional dict with column:value filters for starting category
            start_from: Optional path to start from
        """
        self.create_session()
        self.storage.create_products_table()
        
        paths = self.get_paths(category_filter=category_filter, start_from=start_from)
        
        for idx, path in enumerate(paths, 1):
            print(f"\n[{idx}/{len(paths)}] Scraping: {path}")
            products_data = self.scrape_category(path)
            self.storage.insert_products(products_data)
            self.polite_sleep()
        
        print("\nScraping completed!")
