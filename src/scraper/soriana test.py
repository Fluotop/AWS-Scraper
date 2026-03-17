import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urlparse

SITEMAP_URL = "https://www.soriana.com/sitemap_11-category.xml"
STORE_SLUG = "soriana"

scraper = cloudscraper.create_scraper()
response = scraper.get(SITEMAP_URL)

soup = BeautifulSoup(response.text, "xml")

urls = [loc.text.strip() for loc in soup.find_all("loc")]

categories = []
id_counter = 1000  # starting ID (you can change)

url_to_id = {}

def clean_name(slug):
    name = slug.replace("-", " ").title()
    return name

for url in urls:
    parsed = urlparse(url)
    path = parsed.path.strip("/")   # example: vinos-licores-y-cervezas/vinos
    parts = path.split("/")

    parent_id = 0
    full_path = ""
    
    for level, part in enumerate(parts, start=1):
        full_path += f"/{part}"
        
        if full_path not in url_to_id:
            id_counter += 1
            url_to_id[full_path] = id_counter
            
            categories.append({
                "id": id_counter,
                "store": STORE_SLUG,
                "name": clean_name(part),
                "parent_id": parent_id,
                "path": full_path + "/",
                "level": level
            })
        
        parent_id = url_to_id[full_path]

# Print in your required format
for c in categories:
    print(
        f"{c['id']}\t{c['store']}\t{c['name']}\t"
        f"{c['parent_id']}\t{c['path']}\t{c['level']}"
    )