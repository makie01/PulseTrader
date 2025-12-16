import json
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from .prompt import EVENT_FINDER_AGENT_PROMPT

# Tools built for Events Agent
from tools.kalshi_events import search_open_events
from tools.kalshi_markets import get_markets_for_event as _get_markets_for_event


def find_kalshi_events(topic: str, limit: int = 5) -> dict:
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


def _filter_market_data(market: dict) -> dict:
    """
    Filter market data to only include fields relevant for LLM decision-making.
    
    Fields are logically grouped:
    1. Identifiers: event_ticker, ticker, market_type
    2. Descriptions: title, subtitle, yes_sub_title, no_sub_title
    3. Current Pricing: yes_ask, no_ask
    4. Previous Pricing: previous_yes_ask, previous_no_ask
    5. Timing: created_time, open_time, close_time, expiration_time, settlement_timer_seconds
    6. Rules & Conditions: rules_primary, rules_secondary, early_close_condition, can_close_early
    7. Trading Activity: volume, volume_24h, open_interest, liquidity_dollars
    8. Market Structure: tick_size, floor_strike, cap_strike, functional_strike, custom_strike, price_ranges
    9. Status & Results: status, result, category
    10. Other: primary_participant_key
    """
    return {
        # Identifiers
        "event_ticker": market.get("event_ticker"),
        "ticker": market.get("ticker"),
        "market_type": market.get("market_type"),
        
        # Descriptions
        "title": market.get("title"),
        "subtitle": market.get("subtitle"),
        "yes_sub_title": market.get("yes_sub_title"),
        "no_sub_title": market.get("no_sub_title"),
        
        # Current Pricing
        "yes_ask": market.get("yes_ask"),  # Price in cents
        "no_ask": market.get("no_ask"),    # Price in cents
        
        # Previous Pricing
        "previous_yes_ask": market.get("previous_yes_ask"),
        "previous_no_ask": market.get("previous_no_ask"),
        
        # Timing
        "created_time": market.get("created_time"),
        "open_time": market.get("open_time"),
        "close_time": market.get("close_time"),
        "expiration_time": market.get("expiration_time"),
        "settlement_timer_seconds": market.get("settlement_timer_seconds"),
        
        # Rules & Conditions
        "rules_primary": market.get("rules_primary"),
        "rules_secondary": market.get("rules_secondary"),
        "early_close_condition": market.get("early_close_condition"),
        "can_close_early": market.get("can_close_early"),
        
        # Trading Activity
        "volume": market.get("volume"),
        "volume_24h": market.get("volume_24h"),
        "open_interest": market.get("open_interest"),
        "liquidity_dollars": market.get("liquidity_dollars"),
        
        # Market Structure
        "tick_size": market.get("tick_size"),
        "floor_strike": market.get("floor_strike"),
        "cap_strike": market.get("cap_strike"),
        "functional_strike": market.get("functional_strike"),
        "custom_strike": market.get("custom_strike"),
        "price_ranges": market.get("price_ranges"),
        
        # Status & Results
        "status": market.get("status"),
        "result": market.get("result"),
        "category": market.get("category"),
        
        # Other
        "primary_participant_key": market.get("primary_participant_key"),
    }


def get_event_markets(event_ticker: str) -> dict:
    """
    Retrieve all **open** markets for a given Kalshi event ticker.

    Args:
        event_ticker: Full event ticker, e.g. "KXGOVTSPEND-26".

    Returns:
        dict with:
        - event_ticker
        - markets: list of filtered market dicts (only essential fields for LLM)
    """
    
    markets = _get_markets_for_event(event_ticker=event_ticker)
    print("event_ticker: ", event_ticker)
    print("markets: ", markets)
    
    # Filter markets to only include relevant fields
    filtered_markets = [_filter_market_data(market) for market in markets]
    
    # Prepare the data to save
    result_data = {
        "event_ticker": event_ticker,
        "markets": filtered_markets,
    }
    
    return result_data


find_kalshi_events_tool = FunctionTool(find_kalshi_events)
get_event_markets_tool = FunctionTool(get_event_markets)


event_finder_agent = Agent(
    name='event_finder_agent',
    model='gemini-2.5-pro',
    description="Finds relevant Kalshi events based on user's interests and can retrieve markets for a specific event.",
    instruction=EVENT_FINDER_AGENT_PROMPT,
    tools=[find_kalshi_events_tool, get_event_markets_tool],
)
