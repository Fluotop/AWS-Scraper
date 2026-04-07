"""
Drift-detection test for SuperakiScraper._parse_product().

Strategy:
  1. Fetch the live API endpoint for category 110101 (limit=1).
  2. Run _parse_product() against the first product.
  3. Assert every extracted field matches the snapshot recorded on 2026-04-07.

Run with:  pytest tests/test_superaki_scraper.py -v
"""
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from src.scraper.scrapers.superaki_scraper_new import SuperakiScraper

# ---------------------------------------------------------------------------
# Snapshot values recorded on 2026-04-07
# ---------------------------------------------------------------------------
SNAPSHOT = {
    "product_id":             61864,
    "store_name":             "superaki",
    "name":                   "STILA QUAKER BARRAS DE AVENA FIT FRUTOS ROJOS",
    "brand":                  "STILA",
    "maincat":                "Barras de cereales",
    "cat":                    "Abarrotes",
    "subcat":                 None,          # only 2 categories in response
    "catid":                  110101,
    # partial prefixes
    "image_url_prefix":       "https://cdn-superaki.aktiosdigitalservices.com/tol/superaki/media/product/img/300x300/",
    "link_prefix":            "https://www.superaki.mx/",
}

LIVE_URL = (
    "https://www.superaki.mx/api/rest/V1.0/catalog/product"
    "?categories=110101&page=1&limit=1&offset=0"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.superaki.mx/",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scraper():
    """SuperakiScraper instance with no storage (parse-only)."""
    instance = SuperakiScraper.__new__(SuperakiScraper)
    instance.store_name = "superaki"
    return instance


@pytest.fixture(scope="module")
def live_result(scraper):
    """
    Fetch the live API, run _parse_product() on the first product, and
    return the resulting tuple. Skips the module if the endpoint is unreachable.
    """
   
    resp = requests.get(LIVE_URL, headers=HEADERS, timeout=15)

    data = resp.json()
    products = data.get("products", [])
    assert len(products) == 1, \
        f"Expected exactly 1 product from the API, got {len(products)}"

    return scraper._parse_product(products[0])


# ---------------------------------------------------------------------------
# Individual field assertions — each maps to one tuple position
# ---------------------------------------------------------------------------

def test_product_id(live_result):
    assert live_result[0] == SNAPSHOT["product_id"], \
        f"product_id drifted got: {live_result[0]!r}"

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
