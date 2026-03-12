import cloudscraper
from bs4 import BeautifulSoup

BASE = "https://www.soriana.com"

url = "https://www.soriana.com/vinos-licores-y-cervezas/destilados-y-licores/brandy-y-cognac/"

scraper = cloudscraper.create_scraper()
response = scraper.get(url)

soup = BeautifulSoup(response.text, "html.parser")

products = soup.find_all("div", class_="product")

for product in products:
    pid = product.get("data-pid")

    name_tag = product.select_one("a.product-tile--link")
    name = name_tag.get_text(strip=True) if name_tag else None
    link = BASE + name_tag["href"] if name_tag else None

    price_tag = product.select_one("span.cart-price")
    price = price_tag.get_text(strip=True) if price_tag else None

    image_tag = product.select_one("img.tile-image")
    image_url = image_tag["src"] if image_tag else None

    print({
        "pid": pid,
        "name": name,
        "price": price,
        "url": link,
        "image": image_url
    })