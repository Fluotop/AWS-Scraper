from history_layer import run_history

SOURCE_PREFIX  = "scraper/athena-results/discounts/"
HISTORY_PREFIX = "scraper/athena-results/discounts_history/"


def lambda_handler(event, context):
    return run_history(SOURCE_PREFIX, HISTORY_PREFIX)
