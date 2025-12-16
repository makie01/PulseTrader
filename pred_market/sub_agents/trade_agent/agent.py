from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from .prompt import EXECUTION_AGENT_PROMPT
from tools.kalshi_trade import execute_kalshi_trade as _execute_kalshi_trade


def execute_kalshi_trade(
    ticker: str,
    side: str,
    quantity: int,
    price: int = None
) -> dict:
    """
    Execute a trade on Kalshi prediction markets. Trades are always market orders.
    
    Args:
        ticker: Market ticker to trade (e.g., "RAIN_SF")
        side: "yes" or "no"
        quantity: Number of contracts to trade
        price: Price in cents, maximum you're okay paying
    Returns:
        dict: Response with order confirmation from Kalshi API
    """
    # Use the actual implementation from tools.kalshi_trade
    # Note: The current implementation uses market orders and requires price
    if price is None:
        raise ValueError("Price is required for trade execution")
    
    resp = _execute_kalshi_trade(ticker=ticker, side=side, quantity=quantity, price=price)
    return resp


execute_kalshi_trade_tool = FunctionTool(execute_kalshi_trade)


execution_agent = Agent(
    name='execution_agent',
    model='gemini-2.5-pro',
    description="Places trades on Kalshi prediction markets ONLY when the user clearly requests execution and confirms.",
    instruction=EXECUTION_AGENT_PROMPT,
    tools=[execute_kalshi_trade_tool],
)
