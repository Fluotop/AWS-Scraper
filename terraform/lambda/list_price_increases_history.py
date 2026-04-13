from history_layer import run_history

SOURCE_PREFIX  = "scraper/athena-results/list_price_increases/"
HISTORY_PREFIX = "scraper/athena-results/list_price_increases_history/"


def lambda_handler(event, context):
    return run_history(SOURCE_PREFIX, HISTORY_PREFIX)
