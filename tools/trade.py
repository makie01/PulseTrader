import sys
from pathlib import Path
from kalshi_python_sync import Configuration, ApiClient
from kalshi_python_sync.api import orders_api
from kalshi_python_sync.models import CreateOrderRequest

# Handle both package import and direct execution
try:
    from .kalshi_client import get_kalshi_client
except ImportError:
    # When running directly, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.kalshi_client import get_kalshi_client

def execute_kalshi_trade(ticker, side, quantity, price):
    client = get_kalshi_client()
    orders = orders_api.OrdersApi(client)
    resp = orders.create_order(
        ticker=ticker,
        side=side.lower(),
        action="buy", 
        count=quantity,
        type="market",
        yes_price=price,
        time_in_force="immediate_or_cancel",
    )
    print(resp)
    return resp

if __name__ == "__main__":
    execute_kalshi_trade("KXRECOGROC-29", "yes", 1, 10)
    
