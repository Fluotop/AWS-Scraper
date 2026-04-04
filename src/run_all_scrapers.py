"""Run all configured scrapers together.

This script runs the Chedraui and Superaki scrapers using the same storage backend.

To switch between local DuckDB storage and AWS S3 storage, edit the configuration block below.
"""

import threading

from scraper.scrapers.chedraui_scraper_new import ChedrauiScraper
from scraper.scrapers.superaki_scraper_new import SuperakiScraper

# ---------------------------------------------------------------------------
# CONFIGURATION - edit these values to switch storage / resume from a category
# ---------------------------------------------------------------------------
STORAGE_TYPE = "aws"  # "local" or "aws"
PRODUCTS_DB = "products.duckdb"  # used when STORAGE_TYPE == "local"
CATEGORIES_DB = "categories.duckdb"
AWS_BUCKET = "bdm060897-prod"  # required when STORAGE_TYPE == "aws"
AWS_PREFIX = "scraper/products"  # prefix/key prefix for parquet files

# Per-scraper resume & category filters (scraper-specific)
# Each scraper can have its own `start_from` path and `category_filter`.
# Set to None to scrape all categories (or start from beginning).
CHEDRAUI_START_FROM = None
#CHEDRAUI_CATEGORY_FILTER = {"name": "Supermercado", "level": "1"}
CHEDRAUI_CATEGORY_FILTER = None

SUPERAKI_START_FROM = None
SUPERAKI_CATEGORY_FILTER = None


def _make_scrapers():
    if STORAGE_TYPE == "aws" and not AWS_BUCKET:
        raise ValueError("AWS_BUCKET must be set when STORAGE_TYPE is 'aws'.")

    return [
        {
            "scraper": ChedrauiScraper(
                storage_type=STORAGE_TYPE,
                products_db=PRODUCTS_DB,
                categories_db=CATEGORIES_DB,
                aws_bucket=AWS_BUCKET,
                aws_prefix=AWS_PREFIX,
            ),
            "category_filter": CHEDRAUI_CATEGORY_FILTER,
            "start_from": CHEDRAUI_START_FROM,
        },
        {
            "scraper": SuperakiScraper(
                storage_type=STORAGE_TYPE,
                products_db=PRODUCTS_DB,
                categories_db=CATEGORIES_DB,
                aws_bucket=AWS_BUCKET,
                aws_prefix=AWS_PREFIX,
            ),
            "category_filter": SUPERAKI_CATEGORY_FILTER,
            "start_from": SUPERAKI_START_FROM,
        },
    ]


def _run_scraper(scraper, category_filter=None, start_from=None):
    scraper.run(category_filter=category_filter, start_from=start_from)


class ScraperThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error = None

    def run(self):
        try:
            super().run()
        except Exception as exc:
            self.error = exc


def main():
    scraper_configs = _make_scrapers()

    threads = []
    for cfg in scraper_configs:
        t = ScraperThread(
            target=_run_scraper,
            args=(
                cfg["scraper"],
                cfg.get("category_filter"),
                cfg.get("start_from"),
            ),
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    failed_threads = [t for t in threads if t.error is not None]
    if failed_threads:
        errors = "; ".join(f"{t.name}: {t.error}" for t in failed_threads)
        raise RuntimeError(f"One or more scraper threads failed: {errors}")


if __name__ == "__main__":
    main()
