from kalshi_client import get_kalshi_client
from pprint import pprint
import json

client = get_kalshi_client()

limit = 100 # int | Number of results per page. Defaults to 100. Maximum value is 1000. (optional) (default to 100)

cursor = None # 'cursor_example' # str | Pagination cursor. Use the cursor value returned from the previous response to get the next page of results. Leave empty for the first page. (optional)

event_ticker = None # 'event_ticker_example' # str | Filter by event ticker (optional)

series_ticker = None # 'series_ticker_example' # str | Filter by series ticker (optional)

max_close_ts = None #56 # int | Filter items that close before this Unix timestamp (optional)

min_close_ts = None #56 # int | Filter items that close after this Unix timestamp (optional)

status = None#'initialized' # str | Filter by market status. Comma-separated list. Possible values are 'initialized', 'open', 'closed', 'settled', 'determined'. Note that the API accepts 'open' for filtering but returns 'active' in the response. Leave empty to return markets with any status. (optional)

tickers = None # str | Filter by specific market tickers. Comma-separated list of market tickers to retrieve. (optional)

try:
    # Get Markets
    api_response = client.get_markets(limit=limit, cursor=cursor, event_ticker=event_ticker, series_ticker=series_ticker, max_close_ts=max_close_ts, min_close_ts=min_close_ts, status=status, tickers=tickers)
    print("The response of MarketsApi->get_markets:\n")
    print(api_response.markets[0])
except Exception as e:
    print("Exception when calling MarketsApi->get_markets: %s\n" % e)