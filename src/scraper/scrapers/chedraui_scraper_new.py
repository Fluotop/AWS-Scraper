import requests
from datetime import date
from scraper.scrapers.base_scraper import BaseScraper
from playwright.sync_api import sync_playwright

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
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.chedraui.com.mx", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            cookies = {c["name"]: c["value"] for c in context.cookies()}
            browser.close()

        session = requests.Session()
        session.cookies.set("vtex_session", cookies["vtex_session"], domain=".chedraui.com.mx")
        session.cookies.set(
            "vtex_segment",
            "eyJjYW1wYWlnbnMiOm51bGwsImNoYW5uZWwiOiIxIiwicHJpY2VUYWJsZXMiOm51bGwsInJlZ2lvbklkIjoiVTFjalkyaGxaSEpoZFdsdGVEQXlOVFU9IiwidXRtX2NhbXBhaWduIjpudWxsLCJ1dG1fc291cmNlIjpudWxsLCJ1dG1pX2NhbXBhaWduIjpudWxsLCJjdXJyZW5jeUNvZGUiOiJNWE4iLCJjdXJyZW5jeVN5bWJvbCI6IiQiLCJjb3VudHJ5Q29kZSI6Ik1FWCIsImN1bHR1cmVJbmZvIjoiZXMtTVgiLCJjaGFubmVsUHJpdmFjeSI6InB1YmxpYyIsImZhY2V0cyI6ImNvdW50cnk9TUVYO2Nvb3JkaW5hdGVzPS04Ni44NDA5MSwyMS4xNTM1MTsifQ",
            domain=".chedraui.com.mx"
        )

        self.session = session
        return session
    
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
                                    .get("priceWithoutDiscount")
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
