import requests
import base64
import json
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
    
    LATITUDE  = 21.15351
    LONGITUDE = -86.84091
    # When the regions API returns multiple sellers, only keep the one whose name
    # contains this keyword. Prevents promotional prices from nearby stores bleeding in.
    STORE_SELLER_KEYWORD = "KABAH"

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
    
    def _get_region_id(self) -> str:
        """Fetch the VTEX regionId for the configured coordinates.

        If STORE_SELLER_KEYWORD is set, returns a single-seller regionId matching
        only that store, so promotions from other nearby sellers don't affect prices.
        """
        r = requests.get(
            "https://www.chedraui.com.mx/api/checkout/pub/regions",
            params={
                "country": "MEX",
                "geoCoordinates": f"{self.LONGITUDE};{self.LATITUDE}",
            },
            headers=self.HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        if self.STORE_SELLER_KEYWORD:
            keyword = self.STORE_SELLER_KEYWORD.upper()
            for region in data:
                for seller in region.get("sellers", []):
                    if keyword in seller["name"].upper():
                        single = f"SW#{seller['id']}"
                        return base64.b64encode(single.encode()).decode().rstrip("=")
            all_sellers = [s["name"] for r in data for s in r.get("sellers", [])]
            raise RuntimeError(
                f"STORE_SELLER_KEYWORD '{self.STORE_SELLER_KEYWORD}' not found in regions API. "
                f"Available sellers: {all_sellers}"
            )

        return data[0]["id"]

    # --------------------------------------------------
    # CREATE SESSION FOR CHEDRAUI
    # --------------------------------------------------
    def create_session(self):
        region_id = self._get_region_id()
        print(f"Region ID: {region_id}")

        # Get vtex_session/vtex_segment cookies via a headless browser with geolocation
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                geolocation={"latitude": self.LATITUDE, "longitude": self.LONGITUDE},
                permissions=["geolocation"],
            )
            page = ctx.new_page()
            page.goto("https://www.chedraui.com.mx", timeout=120000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            cookies = {c["name"]: c["value"] for c in ctx.cookies()}
            browser.close()

        # Patch vtex_segment with the correct regionId and location facets, then re-encode
        if "vtex_segment" not in cookies:
            raise RuntimeError(f"vtex_segment cookie not found. Available cookies: {list(cookies.keys())}")
        seg = json.loads(base64.b64decode(cookies["vtex_segment"] + "=="))
        seg["regionId"] = region_id
        seg["facets"] = f"country=MEX;coordinates={self.LONGITUDE},{self.LATITUDE};"
        new_seg = base64.b64encode(json.dumps(seg, separators=(",", ":")).encode()).decode().rstrip("=")

        session = requests.Session()
        session.cookies.set("vtex_session", cookies["vtex_session"], domain=".chedraui.com.mx")
        session.cookies.set("vtex_segment", new_seg, domain=".chedraui.com.mx")
        # Send regionId as a header so catalog API uses local pricing even if vtex_session
        # was captured before geolocation was fully applied
        self.HEADERS["x-vtex-region"] = region_id

        self.session = session
        return session
    
    SIM_URL = "https://www.chedraui.com.mx/api/checkout/pub/orderForms/simulation"

    def _simulate_prices(self, sku_ids: list) -> dict:
        """Call checkout simulation for a batch of SKU IDs.

        Returns a dict mapping sku_id -> {"price": ..., "list_price": ...} in pesos.
        Falls back gracefully: missing SKUs are simply absent from the dict.
        """
        payload = {
            "items": [{"id": sku_id, "quantity": 1, "seller": "1"} for sku_id in sku_ids],
            "country": "MEX",
            "geoCoordinates": [self.LONGITUDE, self.LATITUDE],
        }
        try:
            r = self.session.post(self.SIM_URL, json=payload, headers=self.HEADERS, timeout=15)
            r.raise_for_status()
            return {
                item["id"]: {
                    "price": item["price"] / 100,
                    "list_price": item["listPrice"] / 100,
                }
                for item in r.json().get("items", [])
                if item.get("availability") == "available" and item.get("price") is not None
            }
        except Exception as exc:
            print(f"[chedraui] simulation failed, using catalog prices: {exc}")
            return {}

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

            # Simulate prices for this page's SKUs to get accurate in-store prices
            sku_ids = [p["items"][0]["itemId"] for p in products if p.get("items")]
            sim_prices = self._simulate_prices(sku_ids)

            for product in products:
                product_data = self._parse_product(product, sim_prices)
                products_to_insert.append(product_data)
            
            if len(products) < self.PAGE_SIZE:
                break
            
            page += 1
            self.polite_sleep()
        
        return products_to_insert
    
    def _parse_product(self, product: dict, sim_prices: dict = None) -> tuple:
        """
        Parse a product JSON from Chedraui API into a database tuple.

        sim_prices: optional dict of {sku_id: {price, list_price}} from checkout simulation.
        When present, all three price fields are overridden with the accurate in-store Kabah
        values, because the catalog API can return wrong prices for in-store-only products.
        """
        product_id = product.get("productId")
        name = product.get("productName")
        brand = product.get("brand")
        maincat = product.get("categories", None)[0]
        cat = product.get("categories", None)[1]
        subcat = product.get("categories", None)[2]
        catid = product.get("categoriesIds", None)[0]
        item = product.get("items")[0]
        sku_id = item["itemId"]
        image = (item.get("images") or [{}])[0].get("imageUrl")
        offer = item.get("sellers")[0].get("commertialOffer", {})

        price = offer.get("Price")
        price_without_discount = offer.get("PriceWithoutDiscount")
        list_price = offer.get("ListPrice")
        is_available = offer.get("IsAvailable")

        # Override with simulation prices when available (accurate in-store Kabah prices).
        # Also derive is_available from the simulation: if the SKU is present in sim_prices
        # it means the simulation returned availability="available", which is more reliable
        # than the catalog IsAvailable field (which can be poisoned by vtex_session cookies).
        if sim_prices is not None:
            if sku_id in sim_prices:
                sim = sim_prices[sku_id]
                price = sim["price"]
                price_without_discount = sim["price"]
                list_price = sim["list_price"]
                is_available = True
            else:
                is_available = False

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
        category_filter=None,
        start_from=START_FROM,
    )


if __name__ == "__main__":
    main()
