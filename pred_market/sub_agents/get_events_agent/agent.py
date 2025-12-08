from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from .prompt import EVENT_FINDER_AGENT_PROMPT


def find_kalshi_markets(topic: str, limit: int = 10) -> dict:
    """
    Placeholder function to find Kalshi markets based on topic.
    
    Args:
        topic: The topic or interest area to search for (e.g., "weather", "inflation", "elections")
        limit: Maximum number of markets to return
        
    Returns:
        dict: Placeholder response with market information
    """
    # Placeholder implementation - returns empty structure
    return {
        "markets": [],
        "topic": topic,
        "limit": limit,
        "message": "Placeholder: Market discovery not yet implemented"
    }


find_kalshi_markets_tool = FunctionTool(find_kalshi_markets)

event_finder_agent = Agent(
    name='event_finder_agent',
    model='gemini-2.5-pro',
    description="Finds relevant Kalshi markets based on user's interests and topics.",
    instruction=EVENT_FINDER_AGENT_PROMPT,
    tools=[find_kalshi_markets_tool],
)

