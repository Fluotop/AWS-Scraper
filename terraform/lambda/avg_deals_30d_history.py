from history_layer import run_history

SOURCE_PREFIX  = "scraper/athena-results/avg_deals_30d/"
HISTORY_PREFIX = "scraper/athena-results/avg_deals_30d_history/"


def lambda_handler(event, context):
    return run_history(SOURCE_PREFIX, HISTORY_PREFIX)
