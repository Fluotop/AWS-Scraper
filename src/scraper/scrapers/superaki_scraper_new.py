import requests
import json
from datetime import date, datetime, timedelta
from scraper.scrapers.base_scraper import BaseScraper

# --------------------------------------------------
# SUPERAKI SCRAPER CLASS
# --------------------------------------------------
class SuperakiScraper(BaseScraper):
    """Scraper for Superaki store."""
    
    BASE_URL = "https://www.superaki.mx/api/rest/V1.0/catalog/product"
    BASE_DELAY = 1.5
    PAGE_SIZE = 20
    MAX_RETRIES = 3
    
    def __init__(
        self,
        storage=None,
        products_db: str = "products.duckdb",
        categories_db: str = "categories.duckdb",
        storage_type: str = "local",
        aws_bucket: str = None,
        aws_prefix: str = "products",
    ):
        super().__init__(
            store_name="superaki",
            storage=storage,
            products_db=products_db,
            categories_db=categories_db,
            storage_type=storage_type,
            aws_bucket=aws_bucket,
            aws_prefix=aws_prefix,
        )
        self.HEADERS = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.superaki.mx/"
        }
    
    # --------------------------------------------------
    # CREATE SESSION FOR SUPERAKI
    # --------------------------------------------------
    def create_session(self):
        """Create and configure a requests session for Superaki."""
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
    
    # --------------------------------------------------
    # SCRAPE ONE CATEGORY
    # --------------------------------------------------
    def scrape_category(self, path: str):
        """
        Scrape products from a Superaki category.
        
        Args:
            path: Category path to scrape
            
        Returns:
            List of tuples with product data
        """
        print(f"\nScraping category path: {path}")
        category_id = path.strip("/").split("/")[-1]
        products_to_insert = []
        page = 1
        offset = 0
        with open("status.txt", "w") as f:
            f.write(self.store_name + " - " + path)
        while True:
            params = {
                "categories": category_id,
                "page": page,
                "limit": self.PAGE_SIZE,
                "offset": offset,
            }
            
            response = self.safe_get(self.BASE_URL, params)
            
            if response is None:
                page += 1
                self.polite_sleep()
                continue
            
            response_data = response.json()
            products = response_data.get("products", [])
            print(response.url)
            total_count = response_data.get("totalCount", 0)
            
            for product in products:
                product_data = self._parse_product(product)
                products_to_insert.append(product_data)
            
            page += 1
            offset += self.PAGE_SIZE
            
            if offset >= total_count:
                print("Finished scraping all products.")
                break
            
            self.polite_sleep()
        
        return products_to_insert
    
    def _parse_product(self, product: dict) -> tuple:
        """
        Parse a product JSON from Superaki API into a database tuple.
        
        Args:
            product: Product JSON object
            
        Returns:
            Tuple with product data
        """
        product_data = product.get("productData") or {}
        categories = product.get("categories") or []
        media = product.get("media") or []
        prices = (product.get("priceData") or {}).get("prices") or []
        
        # Basic fields
        product_id = product.get("id")
        name = product_data.get("name")
        brand = (product_data.get("brand") or {}).get("name")
        link = product_data.get("url")
        
        # Categories
        maincat = categories[0].get("name") if len(categories) > 0 else None
        cat = categories[1].get("name") if len(categories) > 1 else None
        subcat = categories[2].get("name") if len(categories) > 2 else None
        catid = categories[0].get("id") if categories else None
        
        # Image
        image = media[0].get("url") if media else None
        
        # Prices
        price = None
        price_without_discount = None
        list_price = None
        
        for p in prices:
            if p.get("id") == "PRICE":
                price_without_discount = p.get("value", {}).get("centUnitAmount")
                list_price = price_without_discount
                price = price_without_discount
            elif p.get("id") == "OFFER_PRICE":
                price = p.get("value", {}).get("centUnitAmount")
        
        is_available = product_data.get("availability")
        scrape_date = date.today()
        
        return (
            product_id, self.store_name, scrape_date, name, brand, maincat, cat, subcat,
            catid, image, price, price_without_discount, list_price, is_available, link
        )


def main():
    """Run the Superaki scraper."""
    scraper = SuperakiScraper()
    scraper.run()


if __name__ == "__main__":
    main()
