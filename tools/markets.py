import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Handle both package import and direct execution
try:
    from .kalshi_client import get_kalshi_client
except ImportError:
    # When running directly, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.kalshi_client import get_kalshi_client


def market_to_dict(market: Any) -> Dict[str, Any]:
    """
    Convert a Kalshi Market model to a plain dict, handling different SDK versions.
    """

    return market.model_dump()


def get_markets_for_event(
    event_ticker: str,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Retrieve **all** open markets for a given event ticker, handling pagination.

    Args:
        event_ticker: Full Kalshi event ticker (e.g. "KXELONMARS-99").
        limit: Page size for API calls (max 1000 per Kalshi docs).

    Returns:
        List of market dicts for the specified event.
    """
    client = get_kalshi_client()

    all_markets: List[Dict[str, Any]] = []
    cursor: Optional[str] = None

    while True:
        resp = client.get_markets(
            limit=limit,
            cursor=cursor,
            event_ticker=event_ticker,
            status="open",
        )

        markets = getattr(resp, "markets", []) or []

        # Convert to dicts and *explicitly* keep only markets whose status is "open".
        # This defends against any API/SDK mismatch where non-open statuses
        # (e.g. "inactive") might slip through server-side filters.
        for m in markets:
            m_dict = market_to_dict(m)
            if m_dict.get("status") in ["open", "active"]:
                all_markets.append(m_dict)

        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

    return all_markets


if __name__ == "__main__":
    # Simple manual test: fetch and print markets for a sample event ticker.
    sample_event_ticker = "KXRECOGROC-29"
    markets = get_markets_for_event(sample_event_ticker)
    print(markets)