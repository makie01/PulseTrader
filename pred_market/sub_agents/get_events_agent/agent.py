from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from .prompt import EVENT_FINDER_AGENT_PROMPT
from tools.events import search_open_events
from tools.markets import get_markets_for_event as _get_markets_for_event


def find_kalshi_events(topic: str, limit: int = 10) -> dict:
    """
    Find Kalshi events related to a user-specified topic.

    Args:
        topic: Free-text description of what the user wants to trade/research
               (e.g. "inflation", "NYC weather", "US elections").
        limit: Maximum number of matching events to return.

    Returns:
        A dict with:
        - topic
        - limit
        - total_matches
        - events: list of event dicts (full Kalshi event payload + similarity score)
    """
    events = search_open_events(topic=topic, limit=limit)
    print("topic: ", topic)
    print("events: ", events)
    return events


def get_event_markets(event_ticker: str) -> dict:
    """
    Retrieve all **open** markets for a given Kalshi event ticker.

    Args:
        event_ticker: Full event ticker, e.g. "KXGOVTSPEND-26".

    Returns:
        dict with:
        - event_ticker
        - markets: list of market dicts for that event
    """
    
    markets = _get_markets_for_event(event_ticker=event_ticker)
    print("event_ticker: ", event_ticker)
    print("markets: ", markets)
    return {
        "event_ticker": event_ticker,
        "markets": markets,
    }


find_kalshi_events_tool = FunctionTool(find_kalshi_events)
get_event_markets_tool = FunctionTool(get_event_markets)

event_finder_agent = Agent(
    name='event_finder_agent',
    model='gemini-2.5-pro',
    description="Finds relevant Kalshi events based on user's interests and can retrieve markets for a specific event.",
    instruction=EVENT_FINDER_AGENT_PROMPT,
    tools=[find_kalshi_events_tool, get_event_markets_tool],
)

