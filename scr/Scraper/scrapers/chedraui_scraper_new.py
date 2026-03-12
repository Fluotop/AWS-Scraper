import requests
import json
import base64
from datetime import date
from scrapers.base_scraper import BaseScraper

# --------------------------------------------------
# CHEDRAUI SCRAPER CLASS
# --------------------------------------------------
class ChedrauiScraper(BaseScraper):
    """Scraper for Chedraui store."""
    
    BASE_URL = "https://www.chedraui.com.mx/api/catalog_system/pub/products/search/"
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
            store_name="chedraui",
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
            "Referer": "https://www.chedraui.com.mx/"
        }
    
    # --------------------------------------------------
    # CREATE SESSION FOR CHEDRAUI
    # --------------------------------------------------
    def create_session(self):
        """Create and configure a requests session for Chedraui."""
        self.session = requests.Session()
        
        segment_dict = {
            "campaigns": None,
            "channel": "1",
            "priceTables": None,
            "regionId": "U1cjY2hlZHJhdWlteDAyNzQ=",
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
        
        # Generate fresh VTEX session
        self.session.get("https://www.chedraui.com.mx/", headers=headers)
    
    # --------------------------------------------------
    # SCRAPE ONE CATEGORY
    # --------------------------------------------------
    def scrape_category(self, path: str):
        """
        Scrape products from a Chedraui category.
        
        Args:
            path: Category path to scrape
            
        Returns:
            List of tuples with product data
        """
        print(f"\nScraping category path: {path} (store: {self.store_name})")
        products_to_insert = []
        page = 0
        with open("status.txt", "w") as f:
            f.write(self.store_name + " - " + path)
        
        while True:
            params = {
                "fq": f"C:{path}",
                "_from": page * self.PAGE_SIZE,
                "_to": page * self.PAGE_SIZE + self.PAGE_SIZE - 1,
                "O": "OrderByScoreDESC"
            }
            
            response = self.safe_get(self.BASE_URL, params)
            
            if response is None:
                page += 1
                self.polite_sleep()
                continue
            
            products = response.json()
            print(response.url)
            
            if len(products) < self.PAGE_SIZE:
                break
            
            for product in products:
                product_data = self._parse_product(product)
                products_to_insert.append(product_data)
            
            page += 1
            self.polite_sleep()
        
        return products_to_insert
    
    def _parse_product(self, product: dict) -> tuple:
        """
        Parse a product JSON from Chedraui API into a database tuple.
        
        Args:
            product: Product JSON object
            
        Returns:
            Tuple with product data
        """
        product_id = product.get("productId")
        name = product.get("productName")
        brand = product.get("brand")
        maincat = product.get("categories", None)[0]
        cat = product.get("categories", None)[1]
        subcat = product.get("categories",None)[2]
        catid = product.get("categoriesIds", None)[0]
        image = (product.get("items")[0] \
                        .get("images") or [{}])[0] \
                        .get("imageUrl")
        price = product.get("items")[0] \
                        .get("sellers")[0] \
                        .get("commertialOffer", {}) \
                        .get("Price")
        price_without_discount = product.get("items")[0] \
                                    .get("sellers")[0] \
                                    .get("commertialOffer", {}) \
                                    .get("priceWihoutDiscount")
        list_price = product.get("items")[0] \
                            .get("sellers")[0] \
                            .get("commertialOffer", {}) \
                            .get("ListPrice")
        is_available = product.get("items")[0] \
                            .get("sellers")[0] \
                            .get("commertialOffer", {}) \
                            .get("IsAvailable")
        link = product.get("link")
        scrape_date = date.today()
    
        return (
            product_id, self.store_name, scrape_date, name, brand, maincat, cat, subcat,
            catid, image, price, price_without_discount, list_price, is_available, link
        )



START_FROM = None  # set to a category path (string) to resume from


def main():
    """Run the Chedraui scraper."""

    scraper = ChedrauiScraper()

    scraper.run(
        category_filter={"name": "Supermercado", "level": "1"},
        start_from=START_FROM,
    )


if __name__ == "__main__":
    main()
