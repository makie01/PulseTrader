from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from .prompt import EXECUTION_AGENT_PROMPT


def execute_kalshi_trade(
    ticker: str,
    side: str,
    quantity: int,
    order_type: str,
    price: int = None
) -> dict:
    """
    Placeholder function to execute a trade on Kalshi.
    
    Args:
        ticker: Market ticker to trade (e.g., "RAIN_SF")
        side: "YES" or "NO"
        quantity: Number of contracts to trade
        order_type: "market" or "limit"
        price: Price in cents (required for limit orders, ignored for market orders)
        
    Returns:
        dict: Placeholder response with order confirmation
    """
    # Placeholder implementation - returns empty structure
    return {
        "order_id": None,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "price": price,
        "status": "pending",
        "message": "Placeholder: Trade execution not yet implemented"
    }


execute_kalshi_trade_tool = FunctionTool(execute_kalshi_trade)


execution_agent = Agent(
    name='execution_agent',
    model='gemini-2.5-pro',
    description="Places trades on Kalshi prediction markets ONLY when the user clearly requests execution and confirms.",
    instruction=EXECUTION_AGENT_PROMPT,
    tools=[execute_kalshi_trade_tool],
)

