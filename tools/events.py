from .kalshi_client import get_kalshi_client
import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from .emb import embed_texts, embed_text


def event_to_dict(event: Any) -> Dict[str, Any]:
    """
    Convert a Kalshi Event model to a plain dict
    """
    return event.model_dump()


def fetch_all_open_events(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Fetch all open events from Kalshi (elections environment via get_kalshi_client)
    and return them as a list of plain dicts.
    """
    client = get_kalshi_client()

    all_events: List[Dict[str, Any]] = []
    cursor = None
    status = "open"

    while True:
        resp = client.get_events(limit=limit, cursor=cursor, status=status)

        events = getattr(resp, "events", []) or []
        all_events.extend(event_to_dict(e) for e in events)

        cursor = getattr(resp, "cursor", None)
        if not cursor:
            break

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
DEFAULT_EVENTS_PATH = "data/open_events.json"
DEFAULT_EMBEDS_PATH = "data/open_events_embeds.json"


def _load_open_events_cached(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Fetch all open events from Kalshi, with a simple in-process cache.

    This avoids hitting disk entirely and keeps the implementation fast while
    still returning fresh-ish data (per process lifetime). If you ever want
    stronger freshness guarantees, you can add a TTL or bypass the cache.
    """
    global _EVENTS_CACHE
    if _EVENTS_CACHE is None:
        _EVENTS_CACHE = fetch_all_open_events(limit=limit)
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
    - If index files are missing, fetch from Kalshi and build embeddings once
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
    tickers: List[str] = []
    for ev in events:
        ticker = ev.get("event_ticker") or ev.get("series_ticker")
        if not ticker:
            continue

        title = str(ev.get("title") or "")
        sub_title = str(ev.get("sub_title") or "")
        category = str(ev.get("category") or "")
        text = f"{title}. {sub_title} [category: {category}]"

        tickers.append(ticker)
        texts.append(text)

    if texts:
        vectors = embed_texts(texts)
        embeds = {t: v for t, v in zip(tickers, vectors)}
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
    - Fetch all open events from Kalshi
    - Save them to `events_path`
    - Embed each event and save a small vector index to `embeds_path`

    After this has been run, search_open_events() will load everything from disk,
    which is much faster than re-embedding on each cold start.
    """
    events = fetch_all_open_events()
    save_events_to_json(events, events_path)

    texts: List[str] = []
    tickers: List[str] = []
    for ev in events:
        ticker = ev.get("event_ticker") or ev.get("series_ticker")
        if not ticker:
            continue

        title = str(ev.get("title") or "")
        sub_title = str(ev.get("sub_title") or "")
        category = str(ev.get("category") or "")
        text = f"{title}. {sub_title} [category: {category}]"

        tickers.append(ticker)
        texts.append(text)

    if texts:
        vectors = embed_texts(texts)
        embeds = {t: v for t, v in zip(tickers, vectors)}
    else:
        embeds = {}

    os.makedirs(os.path.dirname(embeds_path) or ".", exist_ok=True)
    with open(embeds_path, "w") as f:
        json.dump(embeds, f)

    # Populate in-process cache as well
    global _EVENTS_CACHE, _EVENT_EMBEDS
    _EVENTS_CACHE = events
    _EVENT_EMBEDS = embeds


def search_open_events(
    topic: str,
    limit: int = 10,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Embedding-based search over all open events using Gemini embeddings.

    - Considers every open event (no hard keyword gate), so paraphrases like
      "United States" vs "U.S. state" can still match.
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
        ticker = ev.get("event_ticker") or ev.get("series_ticker")
        if not ticker:
            continue

        # Optional category filter
        ev_cat = (ev.get("category") or "").lower()
        if cat_set and ev_cat not in cat_set:
            continue

        ev_vec = embeds.get(ticker)
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


if __name__ == "__main__":
    #output_file = "data/open_events.json"
    #events = fetch_all_open_events()
    #save_events_to_json(events, output_file)
    #print(f"Saved {len(events)} open events to {output_file}")
    import time
    start_time = time.time()
    setup_events_index()
    end_time = time.time()
    print(f"Time taken to setup index: {end_time - start_time} seconds")
    start_time = time.time()
    events = search_open_events("elections")
    end_time = time.time()
    print(f"Time taken to search events: {end_time - start_time} seconds")
    for event in events["events"]:
        print("confidence: ", event["score"])
        print("event: ", event)
        print("--------------------------------")