import requests
import json
import base64
import duckdb
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from ..storage.category_storage import (
    BaseCategoryStorage,
    LocalCategoryStorage,
    AWSCategoryStorage,
)


# ---------------------------------------------------------------------------
# CONFIGURATION - edit these values to switch storage between local and AWS
# ---------------------------------------------------------------------------
STORAGE_TYPE = "aws"  # "local" or "aws"
CATEGORIES_DB = "categories.duckdb"
AWS_BUCKET = "bdm060897-prod/scraper"  # required when STORAGE_TYPE == "aws"
AWS_PREFIX = "categories"

# --------------------------------------------------
# BASE CATEGORY MANAGER CLASS
# --------------------------------------------------
class BaseCategoryManager(ABC):
    """Base class for managing store categories."""
    
    def __init__(
        self,
        store_name: str,
        base_url: str,
        api_endpoint: str,
        categories_db: str = "categories.duckdb",
        category_storage: BaseCategoryStorage = None,
        storage_type: str = "local",
        aws_bucket: str = None,
        aws_prefix: str = "categories",
    ):
        """Initialize the category manager.
        
        Args:
            store_name: Name of the store
            base_url: Base URL for the store
            api_endpoint: API endpoint for fetching categories
            categories_db: Path to categories database
            category_storage: Optional category storage backend to use
            storage_type: "local" or "aws" (where to store category DB)
            aws_bucket: S3 bucket name (required when storage_type == "aws")
            aws_prefix: Prefix/folder to store category DB in S3
        """
        self.store_name = store_name
        self.base_url = base_url
        self.api_endpoint = api_endpoint
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
            else:
                self.category_storage = LocalCategoryStorage(db_path=self.categories_db)
    
    @abstractmethod
    def create_session(self):
        """Create and configure a requests session for the store."""
        pass
    
    @abstractmethod
    def extract_category_data(self, data: dict) -> dict:
        """
        Extract and structure category data from API response.
        
        Args:
            data: Raw API response
            
        Returns:
            Dictionary mapping category_id to category info
        """
        pass
    
    def fetch_categories(self):
        """
        Fetch categories from the store's API.
        
        Returns:
            Dictionary with all categories organized by ID
        """
        self.create_session()
        
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self.base_url,
            "Referer": self.base_url,
        }
        
        response = self.session.get(self.api_endpoint, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        return self.extract_category_data(data)
    
    def save_to_database(self, categories: dict):
        """
        Save categories to the database.
        
        Args:
            categories: Dictionary mapping category_id to category info
        """
        sql_categories = []
        for cat_id, data in categories.items():
            sql_categories.append((
                cat_id, data['name'], data['parent'], data['path'],
                data['level'], data['store'], data["link"]
            ))
        
        conn = duckdb.connect(self.categories_db)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT,
            store TEXT,
            name TEXT NOT NULL,
            parent_id TEXT,
            path TEXT,
            level INTEGER,
            link TEXT,
            PRIMARY KEY (id, store)
        )
        """)
        
        conn.executemany("""
        INSERT OR REPLACE INTO categories (id, name, parent_id, path, level, store, link)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sql_categories)
        
        conn.close()

        # Upload the local DuckDB file to remote storage (if configured)
        self.category_storage.upload_local_db()

    def fetch_and_save(self):
        """Fetch categories from API and save to database."""
        categories = self.fetch_categories()
        self.save_to_database(categories)


# --------------------------------------------------
# CHEDRAUI CATEGORY MANAGER
# --------------------------------------------------
class ChedrauiCategoryManager(BaseCategoryManager):
    """Category manager for Chedraui store."""
    
    def __init__(
        self,
        categories_db: str = "categories.duckdb",
        storage_type: str = "local",
        aws_bucket: str = None,
        aws_prefix: str = "categories",
    ):
        super().__init__(
            "chedraui",
            "https://www.chedraui.com.mx",
            "https://www.chedraui.com.mx/api/catalog_system/pub/category/tree/3",
            categories_db,
            storage_type=storage_type,
            aws_bucket=aws_bucket,
            aws_prefix=aws_prefix,
        )
    
    def create_session(self):
        """Create a session with Chedraui segment cookie."""
        self.session = requests.Session()
        
        segment_dict = {
            "campaigns": None,
            "channel": "1",
            "priceTables": None,
            "regionId": "U1cjY2hlZHJhdWlweDAyNzQ=",
            "utm_campaign": None,
            "utm_source": None,
            "utmi_campaign": None,
            "currencyCode": "MXN",
            "currencySymbol": "$",
            "countryCode": "MEX",
            "cultureInfo": "es-MX",
            "channelPrivacy": "public",
            "facets": "country=MEX;coordinates=-86.86575,21.09761;"
        }
        
        segment_encoded = base64.b64encode(
            json.dumps(segment_dict, separators=(",", ":")).encode()
        ).decode()
        
        self.session.cookies.set(
            "vtex_segment",
            segment_encoded,
            domain="www.chedraui.com.mx"
        )
        
        headers = {"User-Agent": "Mozilla/5.0"}
        self.session.get("https://www.chedraui.com.mx/", headers=headers)
    
    def extract_category_data(self, data: dict) -> dict:
        """Extract Chedraui category data."""
        categories = {}
        
        for main in data:
            main_name = main.get("name")
            main_id = main.get("id")
            path = f"/{main_id}/"
            link = f"{self.base_url}/{main_name.replace(' ', '-')}"
            
            categories[main_id] = {
                "name": main_name,
                "parent": None,
                "path": path,
                "level": 1,
                "store": self.store_name,
                "link": link
            }
            
            for child in main.get("children", []):
                sub_name = child.get("name")
                sub_id = child.get("id")
                path = f"/{main_id}/{sub_id}/"
                link = f"{self.base_url}/{main_name.replace(' ', '-')}/{sub_name.replace(' ', '-')}"
                
                categories[sub_id] = {
                    "name": sub_name,
                    "parent": main_id,
                    "path": path,
                    "level": 2,
                    "store": self.store_name,
                    "link": link
                }
                
                for sub_child in child.get("children", []):
                    sub_child_name = sub_child.get("name")
                    sub_child_id = sub_child.get("id")
                    path = f"/{main_id}/{sub_id}/{sub_child_id}/"
                    link = f"{self.base_url}/{main_name.replace(' ', '-')}/{sub_name.replace(' ', '-')}/{sub_child_name.replace(' ', '-')}"
                    
                    categories[sub_child_id] = {
                        "name": sub_child_name,
                        "parent": sub_id,
                        "path": path,
                        "level": 3,
                        "store": self.store_name,
                        "link": link
                    }
        
        return categories


# --------------------------------------------------
# SUPERAKI CATEGORY MANAGER
# --------------------------------------------------
class SuperakiCategoryManager(BaseCategoryManager):
    """Category manager for Superaki store."""
    
    def __init__(
        self,
        categories_db: str = "categories.duckdb",
        storage_type: str = "local",
        aws_bucket: str = None,
        aws_prefix: str = "categories",
    ):
        super().__init__(
            "superaki",
            "https://www.superaki.mx/es/c/",
            "https://www.superaki.mx/api/rest/V1.0/shopping/category/menu",
            categories_db,
            storage_type=storage_type,
            aws_bucket=aws_bucket,
            aws_prefix=aws_prefix,
        )
    
    def create_session(self):
        """Create a session with Superaki location cookie."""
        self.session = requests.Session()
        
        cookie_value = {
            "expireDate": (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z",
            "value": {
                "addressSelectedUnlogged": {
                    "typeSelected": "Shop",
                    "zoneId": 108,
                    "shippingMethod": "T",
                    "zipCode": "77535",
                    "shippingZoneId": "108T"
                }
            }
        }
        
        self.session.cookies.set(
            "CookieTol",
            json.dumps(cookie_value),
            domain="www.superaki.mx"
        )
    
    def extract_category_data(self, data: dict) -> dict:
        """Extract Superaki category data."""
        categories = {}
        
        for main in data:
            main_name = main.get("name")
            main_id = main.get("id")
            path = f"/{main_id}/"
            link = f"{self.base_url}{main_id}/"
            
            categories[main_id] = {
                "name": main_name,
                "parent": None,
                "path": path,
                "level": 1,
                "store": self.store_name,
                "link": link
            }
            
            for child in main.get("subcategories", []):
                sub_name = child.get("name")
                sub_id = child.get("id")
                path = f"/{main_id}/{sub_id}/"
                link = f"{self.base_url}{main_id}/{sub_id}/"
                
                categories[sub_id] = {
                    "name": sub_name,
                    "parent": main_id,
                    "path": path,
                    "level": 2,
                    "store": self.store_name,
                    "link": link
                }
                
                for sub_child in child.get("subcategories", []):
                    sub_child_name = sub_child.get("name")
                    sub_child_id = sub_child.get("id")
                    path = f"/{main_id}/{sub_id}/{sub_child_id}/"
                    link = f"{self.base_url}{main_id}/{sub_id}/{sub_child_id}/"
                    
                    categories[sub_child_id] = {
                        "name": sub_child_name,
                        "parent": sub_id,
                        "path": path,
                        "level": 3,
                        "store": self.store_name,
                        "link": link
                    }
        
        return categories


def main():
    """Fetch and save categories for all stores.

    Configuration is hardcoded via module-level constants so this can be run
    without any CLI or external configuration.
    """

    if STORAGE_TYPE == "aws" and not AWS_BUCKET:
        raise ValueError("AWS_BUCKET must be set when STORAGE_TYPE is 'aws'.")

    chedraui_manager = ChedrauiCategoryManager(
        categories_db=CATEGORIES_DB,
        storage_type=STORAGE_TYPE,
        aws_bucket=AWS_BUCKET,
        aws_prefix=AWS_PREFIX,
    )
    chedraui_manager.fetch_and_save()
    print("Chedraui categories loaded to DB.")

    superaki_manager = SuperakiCategoryManager(
        categories_db=CATEGORIES_DB,
        storage_type=STORAGE_TYPE,
        aws_bucket=AWS_BUCKET,
        aws_prefix=AWS_PREFIX,
    )
    superaki_manager.fetch_and_save()
    print("Superaki categories loaded to DB.")


if __name__ == "__main__":
    main()
