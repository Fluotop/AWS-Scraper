"""
Drift-detection test for ChedrauiScraper._parse_product().

Strategy:
  1. Fetch the live API endpoint for product 3677377.
  2. Find the product in the response by productId.
  3. Run _parse_product() against the live data.
  4. Assert every extracted field matches the value recorded in the snapshot.

Run with:  pytest src/test.py -v
"""
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from src.scraper.scrapers.chedraui_scraper_new import ChedrauiScraper

# ---------------------------------------------------------------------------
# Snapshot values recorded on 2026-04-07
# ---------------------------------------------------------------------------
SNAPSHOT = {
    "product_id":             "3677377",
    "store_name":             "chedraui",
    "name":                   "Té Mccormick Manzanilla con 30 Sobres",
    "brand":                  "McCormick",
    "maincat":                "/Supermercado/Despensa/Cafe y te/",
    "cat":                    "/Supermercado/Despensa/",
    "subcat":                 "/Supermercado/",
    "catid":                  "/1/107/10711/",
    # partial prefixes
    "image_url_prefix":       "https://chedrauimx.vteximg.com.br/arquivos/ids/",
    "link_prefix":            "https://www.chedraui.com.mx/",
}

LIVE_URL = (
    "https://www.chedraui.com.mx/api/catalog_system/pub/products/search/"
    "?fq=C%3A%2F1%2F107%2F10711%2F&_from=0&_to=0&O=OrderByScoreDESC"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.chedraui.com.mx/",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scraper():
    """ChedrauiScraper instance with no storage (parse-only)."""
    instance = ChedrauiScraper.__new__(ChedrauiScraper)
    instance.store_name = "chedraui"
    return instance


@pytest.fixture(scope="module")
def live_result(scraper):
    """
    Fetch the live API, locate product 3677377, run _parse_product(), and
    return the resulting tuple.  The whole test module is skipped if the
    endpoint is unreachable.
    """
    resp = requests.get(LIVE_URL, headers=HEADERS, timeout=15)

    products = resp.json()
    assert isinstance(products, list) and len(products) == 1, \
        f"Expected exactly 1 product from the API, got {len(products) if isinstance(products, list) else type(products).__name__}"

    return scraper._parse_product(products[0])


# ---------------------------------------------------------------------------
# Individual field assertions each maps to one tuple position
# ---------------------------------------------------------------------------

def test_product_id(live_result):
    assert live_result[0] == SNAPSHOT["product_id"], \
        "product_id drifted"

def test_store_name(live_result):
    assert live_result[1] == SNAPSHOT["store_name"], \
        "store_name drifted"

def test_scrape_date_is_today(live_result):
    assert live_result[2] == date.today(), \
        "scrape_date is not today"

def test_name(live_result):
    assert live_result[3] == SNAPSHOT["name"], \
        f"name drifted got: {live_result[3]!r}"

def test_brand(live_result):
    assert live_result[4] == SNAPSHOT["brand"], \
        f"brand drifted got: {live_result[4]!r}"

def test_maincat(live_result):
    assert live_result[5] == SNAPSHOT["maincat"], \
        f"maincat drifted got: {live_result[5]!r}"

def test_cat(live_result):
    assert live_result[6] == SNAPSHOT["cat"], \
        f"cat drifted got: {live_result[6]!r}"

def test_subcat(live_result):
    assert live_result[7] == SNAPSHOT["subcat"], \
        f"subcat drifted got: {live_result[7]!r}"

def test_catid(live_result):
    assert live_result[8] == SNAPSHOT["catid"], \
        f"catid drifted got: {live_result[8]!r}"

def test_image_url(live_result):
    url = live_result[9]
    assert isinstance(url, str) and url.startswith(SNAPSHOT["image_url_prefix"]), \
        f"image_url does not start with {SNAPSHOT['image_url_prefix']!r} got: {url!r}"

def test_price(live_result):
    assert isinstance(live_result[10], (int, float)), \
        f"price is not a number got: {live_result[10]!r}"

def test_price_without_discount(live_result):
    assert isinstance(live_result[11], (int, float)), \
        f"price_without_discount is not a number got: {live_result[11]!r}"

def test_list_price(live_result):
    assert isinstance(live_result[12], (int, float)), \
        f"list_price is not a number got: {live_result[12]!r}"

def test_is_available(live_result):
    assert isinstance(live_result[13], bool), \
        f"is_available is not a boolean – got: {live_result[13]!r}"

def test_link(live_result):
    link = live_result[14]
    assert isinstance(link, str) and link.startswith(SNAPSHOT["link_prefix"]), \
        f"link does not start with {SNAPSHOT['link_prefix']!r} got: {link!r}"
