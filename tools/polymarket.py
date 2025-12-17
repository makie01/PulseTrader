import json
import math
import os
import sys
import time
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Handle both package import and direct execution
try:
    from .emb import embed_texts, embed_text
except ImportError:
    # When running directly, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.emb import embed_texts, embed_text


def fetch_all_open_events(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch all open/active events from Polymarket and return them as a list of dicts.
    
    Uses Polymarket API with query parameters:
    - closed=false: Only fetch events that are not closed
    - limit: Number of events per page
    - offset: For pagination
    
    Args:
        limit: Number of events to fetch per API call (default 100)
    
    Returns:
        List of open/active event dicts
    """
    base_url = "https://gamma-api.polymarket.com/events"
    
    all_events: List[Dict[str, Any]] = []
    offset = 0
    
    try:
        while True:
            # Use query parameters to filter for open events
            params = {
                "order": "id",
                "ascending": "false",
                "closed": "false",  # Only get non-closed events
                "limit": limit,
                "offset": offset
            }
            
            # Add cache-busting headers to ensure fresh data
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
            
            response = requests.get(base_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            events = response.json()
            
            # Check if response is a list or a dict with a list inside
            if isinstance(events, dict):
                # Try common keys that might contain the events list
                events = events.get("data", events.get("events", events.get("results", [])))
            
            if not isinstance(events, list):
                print(f"Warning: Expected list but got {type(events)}")
                break
            
            if len(events) == 0:
                # No more events to fetch
                break
            
            # All events from this endpoint should already be open (closed=false)
            # But we'll still filter to be safe
            for event in events:
                if not isinstance(event, dict):
                    continue
                
                active = event.get("active")
                closed = event.get("closed")
                archived = event.get("archived")
                
                # Filter for open/active events
                if (
                    active is True
                    and closed is False
                    and (archived is False or archived is None)
                ):
                    all_events.append(event)
            
            # If we got fewer events than the limit, we've reached the end
            if len(events) < limit:
                break
            
            # Move to next page
            offset += limit
            
            # Safety limit to prevent infinite loops
            if offset > 10000:  # Max 10k events
                print("Warning: Reached safety limit of 10,000 events")
                break
                
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Polymarket events: {e}")
        return []
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error parsing Polymarket response: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    print(f"Fetched {len(all_events)} open/active events from Polymarket")
    return all_events


def save_events_to_json(events: List[Dict[str, Any]], output_path: str) -> None:
    """
    Save events (list of dicts) to a JSON file, creating parent dirs if needed.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(events, f, indent=2, default=str)


_EVENTS_CACHE: Optional[List[Dict[str, Any]]] = None
_EVENT_EMBEDS: Optional[Dict[str, List[float]]] = None

# Default on-disk locations for the precomputed index
DEFAULT_EVENTS_PATH = "data/polymarket_open_events.json"
DEFAULT_EMBEDS_PATH = "data/polymarket_open_events_embeds.json"


def _load_open_events_cached() -> List[Dict[str, Any]]:
    """
    Fetch all open events from Polymarket, with a simple in-process cache.
    """
    global _EVENTS_CACHE
    if _EVENTS_CACHE is None:
        _EVENTS_CACHE = fetch_all_open_events()
    return _EVENTS_CACHE


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Compute cosine similarity between two dense vectors.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _load_events_and_embeddings(
    events_path: str = DEFAULT_EVENTS_PATH,
    embeds_path: str = DEFAULT_EMBEDS_PATH,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[float]]]:
    """
    Load all open events and their embeddings.

    Preferred fast path:
    - Load both from disk (written by setup_events_index()) and cache in-process.

    Fallback path:
    - If index files are missing, fetch from Polymarket and build embeddings once
      for this process, but do NOT write them to disk.
    """
    global _EVENTS_CACHE, _EVENT_EMBEDS

    # In-process cache already populated
    if _EVENTS_CACHE is not None and _EVENT_EMBEDS is not None:
        return _EVENTS_CACHE, _EVENT_EMBEDS

    # Preferred: load from disk if both files exist
    if os.path.exists(events_path) and os.path.exists(embeds_path):
        with open(events_path, "r") as f:
            events = json.load(f)
        with open(embeds_path, "r") as f:
            embeds = json.load(f)

        _EVENTS_CACHE = events
        _EVENT_EMBEDS = embeds
        return _EVENTS_CACHE, _EVENT_EMBEDS

    # Fallback: build in-memory index for this process only
    events = _load_open_events_cached()

    texts: List[str] = []
    event_ids: List[str] = []
    for ev in events:
        event_id = ev.get("id") or ev.get("ticker") or ev.get("slug")
        if not event_id:
            continue

        title = str(ev.get("title") or "")
        description = str(ev.get("description") or "")
        category = str(ev.get("category") or "")
        # Polymarket events can have series info too
        series_info = ""
        if ev.get("series"):
            series_list = ev.get("series", [])
            if series_list and isinstance(series_list, list) and len(series_list) > 0:
                series_title = series_list[0].get("title", "")
                if series_title:
                    series_info = f" [series: {series_title}]"
        
        text = f"{title}. {description} [category: {category}]{series_info}"

        event_ids.append(str(event_id))
        texts.append(text)

    if texts:
        vectors = embed_texts(texts)
        embeds = {eid: v for eid, v in zip(event_ids, vectors)}
    else:
        embeds = {}

    _EVENTS_CACHE = events
    _EVENT_EMBEDS = embeds

    return _EVENTS_CACHE, _EVENT_EMBEDS


def setup_events_index(
    events_path: str = DEFAULT_EVENTS_PATH,
    embeds_path: str = DEFAULT_EMBEDS_PATH,
) -> None:
    """
    One-time (or occasional) setup:
    - Fetch all open events from Polymarket
    - Save them to `events_path`
    - Embed each event and save a small vector index to `embeds_path`

    After this has been run, search_open_events() will load everything from disk,
    which is much faster than re-embedding on each cold start.
    """
    events = fetch_all_open_events()
    save_events_to_json(events, events_path)

    texts: List[str] = []
    event_ids: List[str] = []
    for ev in events:
        event_id = ev.get("id") or ev.get("ticker") or ev.get("slug")
        if not event_id:
            continue

        title = str(ev.get("title") or "")
        description = str(ev.get("description") or "")
        category = str(ev.get("category") or "")
        # Polymarket events can have series info too
        series_info = ""
        if ev.get("series"):
            series_list = ev.get("series", [])
            if series_list and isinstance(series_list, list) and len(series_list) > 0:
                series_title = series_list[0].get("title", "")
                if series_title:
                    series_info = f" [series: {series_title}]"
        
        text = f"{title}. {description} [category: {category}]{series_info}"

        event_ids.append(str(event_id))
        texts.append(text)

    if texts:
        vectors = embed_texts(texts)
        embeds = {eid: v for eid, v in zip(event_ids, vectors)}
    else:
        embeds = {}

    os.makedirs(os.path.dirname(embeds_path) or ".", exist_ok=True)
    with open(embeds_path, "w") as f:
        json.dump(embeds, f)

    # Populate in-process cache as well
    global _EVENTS_CACHE, _EVENT_EMBEDS
    _EVENTS_CACHE = events
    _EVENT_EMBEDS = embeds


def ensure_events_index_on_disk(
    events_path: str = DEFAULT_EVENTS_PATH,
    embeds_path: str = DEFAULT_EMBEDS_PATH,
) -> None:
    """
    Ensure that the Polymarket events JSON and embeddings index exist on disk.

    - If both files already exist: do nothing.
    - If one or both are missing: build them once via setup_events_index().
    """
    if os.path.exists(events_path) and os.path.exists(embeds_path):
        return
    setup_events_index(events_path=events_path, embeds_path=embeds_path)


def search_open_events(
    topic: str,
    limit: int = 10,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Embedding-based search over all open Polymarket events using Gemini embeddings.

    - Considers every open event (no hard keyword gate), so paraphrases can still match.
    - Keeps everything local to this process: tiny in-memory "vector DB".
    """
    q = (topic or "").strip()
    if not q:
        return {"topic": topic, "limit": limit, "total_matches": 0, "events": []}

    events, embeds = _load_events_and_embeddings()
    query_vec = embed_text(q)
    if not query_vec:
        return {"topic": topic, "limit": limit, "total_matches": 0, "events": []}

    cat_set = {c.lower() for c in categories} if categories else None

    scored: List[Dict[str, Any]] = []
    for ev in events:
        event_id = ev.get("id") or ev.get("ticker") or ev.get("slug")
        if not event_id:
            continue

        # Optional category filter
        ev_cat = (ev.get("category") or "").lower()
        if cat_set and ev_cat not in cat_set:
            continue

        ev_vec = embeds.get(str(event_id))
        if not ev_vec:
            continue

        sim = _cosine_similarity(query_vec, ev_vec)
        if sim <= 0.0:
            continue

        # Return the full event payload plus a similarity score.
        ev_with_score = dict(ev)
        ev_with_score["score"] = sim
        scored.append(ev_with_score)

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[: max(0, limit)]

    return {
        "topic": topic,
        "limit": limit,
        "total_matches": len(scored),
        "events": top,
    }


def get_markets_for_event(
    event_id: Optional[str] = None, # use this one
    event_slug: Optional[str] = None,
    event_ticker: Optional[str] = None,
    event_dict: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve all open/active markets for a given Polymarket event.
    
    Polymarket events already contain a `markets` array, so this function can:
    1. Extract markets from an event dict if provided
    2. Fetch a specific event by ID/slug/ticker and return its markets
    
    Args:
        event_id: Polymarket event ID (numeric string)
        event_slug: Polymarket event slug
        event_ticker: Polymarket event ticker
        event_dict: Full event dict (if you already have it, use this for efficiency)
    
    Returns:
        List of market dicts for the specified event, filtered to active/open markets.
    """
    # If event dict is provided, extract markets directly
    if event_dict:
        markets = event_dict.get("markets", [])
        # Filter for active/open markets
        active_markets = [
            m for m in markets
            if m.get("active") is True and m.get("closed") is False
        ]
        return active_markets
    if event_id:
        print("fetching polymarket event using event_id: ", event_id)
    if event_slug:
        print("fetching polymarket event using event_slug: ", event_slug)
    if event_ticker:
        print("fetching polymarket event using event_ticker: ", event_ticker)

    # Otherwise, fetch the event by ID/slug/ticker
    identifier = event_id or event_slug or event_ticker
    if not identifier:
        return []
    
    # Try to fetch the specific event
    # Polymarket API might support fetching by slug: /events/{slug}
    # Or we can search through all events
    url = f"https://gamma-api.polymarket.com/events/{identifier}"
    
    # Add cache-busting headers and query parameter to ensure fresh data
    headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    # Add timestamp to query string to bust any URL-based caching
    params = {'_t': int(time.time() * 1000)}  # milliseconds timestamp
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            event = response.json()
            markets = event.get("markets", [])
            # Filter for active/open markets
            active_markets = [
                m for m in markets
                if m.get("active") is True and m.get("closed") is False
            ]
            return active_markets
        else:
            # If direct fetch fails, try searching through cached events
            events, _ = _load_events_and_embeddings()
            for ev in events:
                ev_id = str(ev.get("id") or "")
                ev_slug = ev.get("slug") or ""
                ev_ticker = ev.get("ticker") or ""
                
                if (
                    str(identifier) == ev_id
                    or identifier == ev_slug
                    or identifier == ev_ticker
                ):
                    markets = ev.get("markets", [])
                    active_markets = [
                        m for m in markets
                        if m.get("active") is True and m.get("closed") is False
                    ]
                    return active_markets
            
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Polymarket event {identifier}: {e}")
        # Fallback: search through cached events
        events, _ = _load_events_and_embeddings()
        for ev in events:
            ev_id = str(ev.get("id") or "")
            ev_slug = ev.get("slug") or ""
            ev_ticker = ev.get("ticker") or ""
            
            if (
                str(identifier) == ev_id
                or identifier == ev_slug
                or identifier == ev_ticker
            ):
                markets = ev.get("markets", [])
                active_markets = [
                    m for m in markets
                    if m.get("active") is True and m.get("closed") is False
                ]
                return active_markets
        
        return []


if __name__ == "__main__":
    # Test fetching and indexing
    """
    import time
    start_time = time.time()
    setup_events_index()
    end_time = time.time()
    print(f"Time taken to setup index: {end_time - start_time} seconds")
    
    start_time = time.time()
    events = search_open_events("elections")
    end_time = time.time()
    print(f"Time taken to search events: {end_time - start_time} seconds")
    print(f"Found {events['total_matches']} matches")
    for event in events["events"][:5]:  # Show top 5
        print(f"Score: {event['score']:.4f}")
        print(f"Title: {event.get('title', 'N/A')}")
        print(f"Category: {event.get('category', 'N/A')}")
        print("--------------------------------")
    """
    id = "16085"
    print_full_json = True  # Set to True to print full markets JSON, False to only print event title
    
    # Fetch the event to get its title
    url = f"https://gamma-api.polymarket.com/events/{id}"
    headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    params = {'_t': int(time.time() * 1000)}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            event = response.json()
            event_title = event.get('title', 'N/A')
            
            if print_full_json:
                markets = get_markets_for_event(event_id=id)
                print("markets: ")
                print(json.dumps(markets, indent=2))
            else:
                print(f"Event Title: {event_title}")
        else:
            print(f"Error: Could not fetch event {id} (status code: {response.status_code})")
    except Exception as e:
        print(f"Error fetching event: {e}")
    
    