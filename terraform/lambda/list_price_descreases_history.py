from history_layer import run_history

SOURCE_PREFIX  = "scraper/athena-results/list_price_decreases/"
HISTORY_PREFIX = "scraper/athena-results/list_price_decreases_history/"


def lambda_handler(event, context):
    return run_history(SOURCE_PREFIX, HISTORY_PREFIX)
