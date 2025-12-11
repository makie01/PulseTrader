import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Handle both package import and direct execution
try:
    from .arbitrage_poly_kalshi import CROSS_PLATFORM_CANDIDATES_CSV
    from .events import _load_events_and_embeddings as load_kalshi_events_and_embeddings
    from .polymarket import _load_events_and_embeddings as load_polymarket_events_and_embeddings
    from .markets import get_markets_for_event as get_kalshi_markets
    from .polymarket import get_markets_for_event as get_polymarket_markets
except ImportError:
    # When running directly, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.arbitrage_poly_kalshi import CROSS_PLATFORM_CANDIDATES_CSV
    from tools.events import _load_events_and_embeddings as load_kalshi_events_and_embeddings
    from tools.polymarket import _load_events_and_embeddings as load_polymarket_events_and_embeddings
    from tools.markets import get_markets_for_event as get_kalshi_markets
    from tools.polymarket import get_markets_for_event as get_polymarket_markets


# Keys that clearly encode prices / order-book information and should
# be excluded from the LLM description (we only want semantics).
_PRICE_LIKE_KEYS_EXACT = {
    # Kalshi
    "yes_ask",
    "no_ask",
    "yes_bid",
    "no_bid",
    "last_price",
    "last_price_cents",
    "settlement_price",
    # Polymarket
    "bestBid",
    "bestAsk",
    "mid",
    "implied_price",
}

_PRICE_LIKE_SUBSTRINGS = [
    "price",
    "ask",
    "bid",
    "spread",
    "liquidity",
    "volume",
    "fee",
]

_EXCLUDED_TOP_LEVEL_KEYS = {
    # We will fetch markets separately and clean them, so avoid duplicating
    # any raw markets blobs from the event payloads.
    "markets",
}


def _is_price_like_key(key: str) -> bool:
    kl = key.lower()
    if key in _PRICE_LIKE_KEYS_EXACT:
        return True
    for sub in _PRICE_LIKE_SUBSTRINGS:
        if sub in kl:
            return True
    return False


def _sanitize_payload(obj: Any) -> Any:
    """Recursively strip out price-like fields from a dict/list structure.

    We keep everything that helps describe *what* the event/market is about
    (titles, questions, rules, dates, categories, etc.), and remove fields
    that encode current prices / book state.
    """
    if isinstance(obj, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in obj.items():
            if k in _EXCLUDED_TOP_LEVEL_KEYS:
                continue
            if _is_price_like_key(k):
                continue
            cleaned[k] = _sanitize_payload(v)
        return cleaned
    if isinstance(obj, list):
        return [_sanitize_payload(v) for v in obj]
    return obj


def _build_event_indexes() -> Dict[str, Dict[str, Any]]:
    """Build lookup maps for Kalshi and Polymarket events.

    Returns a dict with two keys:
    - "kalshi_by_ticker": {ticker -> event_dict}
    - "polymarket_by_id": {str(id/slug/ticker) -> event_dict}
    """
    kalshi_events, _ = load_kalshi_events_and_embeddings()
    poly_events, _ = load_polymarket_events_and_embeddings()

    kalshi_by_ticker: Dict[str, Dict[str, Any]] = {}
    for ev in kalshi_events:
        ticker = ev.get("event_ticker") or ev.get("series_ticker")
        if ticker:
            kalshi_by_ticker[ticker] = ev

    polymarket_by_id: Dict[str, Dict[str, Any]] = {}
    for ev in poly_events:
        event_id = ev.get("id") or ev.get("ticker") or ev.get("slug")
        if event_id:
            polymarket_by_id[str(event_id)] = ev

    return {
        "kalshi_by_ticker": kalshi_by_ticker,
        "polymarket_by_id": polymarket_by_id,
    }


def load_cross_platform_candidates(
    csv_path: Optional[str] = None,
    min_similarity: float = 0.0,
    max_rows: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load cross-platform event candidates from the CSV produced earlier.

    We only need lightweight metadata here; full event payloads are fetched
    via the Kalshi/Polymarket loaders.
    """
    path = csv_path or CROSS_PLATFORM_CANDIDATES_CSV

    candidates: List[Dict[str, Any]] = []
    try:
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    sim = float(row.get("similarity", "0") or 0.0)
                except ValueError:
                    sim = 0.0
                if sim < min_similarity:
                    continue
                cand = {
                    "kalshi_ticker": row.get("kalshi_ticker"),
                    "polymarket_id": row.get("polymarket_id"),
                    "similarity": sim,
                    # Keep titles/categories around for convenience / debugging.
                    "kalshi_title": row.get("kalshi_title"),
                    "kalshi_sub_title": row.get("kalshi_sub_title"),
                    "kalshi_category": row.get("kalshi_category"),
                    "polymarket_title": row.get("polymarket_title"),
                    "polymarket_category": row.get("polymarket_category"),
                }
                candidates.append(cand)
                if max_rows is not None and len(candidates) >= max_rows:
                    break
    except FileNotFoundError:
        print(f"Candidates CSV not found at {path}. Have you run find_similar_cross_platform_events() yet?")
    return candidates


def build_event_pair_payload(
    candidate: Dict[str, Any],
    kalshi_by_ticker: Dict[str, Dict[str, Any]],
    polymarket_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """For a single CSV candidate, load the corresponding events and markets."""
    kalshi_ticker = candidate.get("kalshi_ticker")
    poly_id = candidate.get("polymarket_id")

    kalshi_event = kalshi_by_ticker.get(kalshi_ticker or "")
    poly_event = polymarket_by_id.get(str(poly_id) if poly_id is not None else "")

    kalshi_markets: List[Dict[str, Any]] = []
    poly_markets: List[Dict[str, Any]] = []

    if kalshi_ticker:
        try:
            kalshi_markets = get_kalshi_markets(kalshi_ticker)
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error fetching Kalshi markets for {kalshi_ticker}: {e}")

    if poly_event is not None:
        try:
            poly_markets = get_polymarket_markets(event_dict=poly_event)
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error fetching Polymarket markets by event_dict for {poly_id}: {e}")

    # Fallback: try fetching by ID if none came back from the event dict
    if not poly_markets and poly_id is not None:
        try:
            poly_markets = get_polymarket_markets(event_id=str(poly_id))
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error fetching Polymarket markets by ID for {poly_id}: {e}")

    return {
        "candidate": candidate,
        "kalshi_event": kalshi_event,
        "polymarket_event": poly_event,
        "kalshi_markets": kalshi_markets,
        "polymarket_markets": poly_markets,
    }


def _summarize_kalshi_event(ev: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Build a compact, human-readable description of a Kalshi event,
    using the key fields we actually care about for semantic matching.
    """
    if not ev:
        return None

    return {
        "event_ticker": ev.get("event_ticker"),
        "series_ticker": ev.get("series_ticker"),
        "title": ev.get("title"),
        "sub_title": ev.get("sub_title"),
        "category": ev.get("category"),
        "strike_date": ev.get("strike_date"),
        "strike_period": ev.get("strike_period"),
        "collateral_return_type": ev.get("collateral_return_type"),
        "mutually_exclusive": ev.get("mutually_exclusive"),
        "available_on_brokers": ev.get("available_on_brokers"),
        # Simple narrative summary similar to existing console output
        "summary": f"{ev.get('title', '')} ({ev.get('sub_title', '').strip()})".strip(),
    }


def _summarize_kalshi_market(m: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compact description of a single Kalshi market, intentionally omitting
    all price/order-book/volume fields while keeping rules, timing, etc.
    """
    if not m:
        return {}

    ticker = m.get("ticker")
    title = m.get("title")
    subtitle = m.get("subtitle")
    yes_sub = m.get("yes_sub_title")
    no_sub = m.get("no_sub_title")

    # Very close to the human-readable logging style:
    #   KX...-250000: Will Bitcoin be above $250000 by Jan 1, 2027 ...?
    summary = f"{ticker}: {title}" if ticker or title else None

    return {
        "ticker": ticker,
        "event_ticker": m.get("event_ticker"),
        "market_type": m.get("market_type"),
        "title": title,
        "subtitle": subtitle,
        "yes_sub_title": yes_sub,
        "no_sub_title": no_sub,
        "status": m.get("status"),
        "category": m.get("category"),
        "open_time": m.get("open_time"),
        "close_time": m.get("close_time"),
        "expiration_time": m.get("expiration_time"),
        "latest_expiration_time": m.get("latest_expiration_time"),
        "early_close_condition": m.get("early_close_condition"),
        "rules_primary": m.get("rules_primary"),
        "rules_secondary": m.get("rules_secondary"),
        "strike_type": m.get("strike_type"),
        "floor_strike": m.get("floor_strike"),
        "cap_strike": m.get("cap_strike"),
        "functional_strike": m.get("functional_strike"),
        "custom_strike": m.get("custom_strike"),
        "summary": summary,
    }


def _summarize_polymarket_event(ev: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Compact description of a Polymarket event, using the key semantic fields.
    """
    if not ev:
        return None

    tags = ev.get("tags") or []
    tag_labels = [t.get("label") for t in tags if isinstance(t, dict) and t.get("label")]

    series_list = ev.get("series") or []
    series_summary = None
    if series_list and isinstance(series_list, list):
        s0 = series_list[0]
        if isinstance(s0, dict):
            series_summary = {
                "title": s0.get("title"),
                "seriesType": s0.get("seriesType"),
                "recurrence": s0.get("recurrence"),
            }

    return {
        "id": ev.get("id"),
        "ticker": ev.get("ticker"),
        "slug": ev.get("slug"),
        "title": ev.get("title"),
        "description": ev.get("description"),
        "startDate": ev.get("startDate"),
        "endDate": ev.get("endDate"),
        "resolutionSource": ev.get("resolutionSource"),
        "tags": tag_labels,
        "series": series_summary,
        # Simple narrative summary
        "summary": ev.get("title"),
    }


def _summarize_polymarket_market(m: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compact description of a Polymarket market, again omitting price-related
    fields while keeping the question, description, outcomes, and timing.
    """
    if not m:
        return {}

    market_id = m.get("id")
    question = m.get("question") or m.get("title")

    summary = f"{market_id}: {question}" if market_id or question else None

    return {
        "id": market_id,
        "slug": m.get("slug"),
        "question": question,
        "description": m.get("description"),
        "outcomes": m.get("outcomes"),
        "resolutionSource": m.get("resolutionSource"),
        "startDate": m.get("startDate"),
        "endDate": m.get("endDate"),
        "eventStartTime": m.get("eventStartTime"),
        "active": m.get("active"),
        "closed": m.get("closed"),
        "summary": summary,
    }


def build_structured_prompt_for_pair(pair_payload: Dict[str, Any]) -> str:
    """Create a structured, human-readable prompt describing both events+markets.

    The description is intentionally simple and close to the console output
    style in arbitrage_cross_finder_fix2_out.txt: short event headers and a
    list of markets with no prices, plus just enough extra info (rules,
    timings, descriptions) to reason about resolution equivalence.
    """
    candidate = pair_payload.get("candidate", {})
    similarity = candidate.get("similarity")
    kalshi_ticker = candidate.get("kalshi_ticker")
    polymarket_id = candidate.get("polymarket_id")

    kalshi_event_raw = pair_payload.get("kalshi_event")
    poly_event_raw = pair_payload.get("polymarket_event")
    kalshi_markets_raw = pair_payload.get("kalshi_markets", []) or []
    poly_markets_raw = pair_payload.get("polymarket_markets", []) or []

    kalshi_event = _summarize_kalshi_event(kalshi_event_raw)
    poly_event = _summarize_polymarket_event(poly_event_raw)
    kalshi_markets = [_summarize_kalshi_market(m) for m in kalshi_markets_raw]
    poly_markets = [_summarize_polymarket_market(m) for m in poly_markets_raw]

    def _trunc(text: Optional[str], limit: int = 120) -> Optional[str]:
        if not text:
            return text
        text = str(text)
        return text if len(text) <= limit else text[: limit - 3] + "..."

    lines: List[str] = []
    lines.append("Event Pair:")
    if similarity is not None:
        try:
            sim_str = f"{float(similarity):.4f}"
        except (TypeError, ValueError):
            sim_str = str(similarity)
        lines.append(f"  Event Similarity: {sim_str}")

    # Kalshi side
    lines.append(f"  Kalshi Event: {kalshi_ticker}")
    if kalshi_event:
        title = kalshi_event.get("title")
        if title:
            lines.append(f"    Title: {title}")
        sub_title = kalshi_event.get("sub_title")
        if sub_title:
            lines.append(f"    Subtitle: {sub_title}")
        category = kalshi_event.get("category")
        if category:
            lines.append(f"    Category: {category}")
        strike_date = kalshi_event.get("strike_date")
        strike_period = kalshi_event.get("strike_period")
        if strike_date or strike_period:
            lines.append(
                f"    Strike info: date={strike_date}, period={strike_period}"
            )

    lines.append(f"    Markets: {len(kalshi_markets)}")
    if kalshi_markets:
        lines.append("    Markets (no prices):")
        for m in kalshi_markets:
            mticker = m.get("ticker")
            mtitle = _trunc(m.get("title"))
            summary_line = f"      {mticker}: {mtitle}..." if mtitle else f"      {mticker}"
            lines.append(summary_line)

            # Do NOT truncate rules / early close text; small details matter
            # for resolution semantics.
            rules = m.get("rules_primary")
            if rules:
                lines.append(f"        Rules: {rules}")
            early_close = m.get("early_close_condition")
            if early_close:
                lines.append(f"        Early close: {early_close}")

    # Polymarket side
    lines.append(f"  Polymarket Event: {polymarket_id}")
    if poly_event:
        ptitle = poly_event.get("title")
        if ptitle:
            lines.append(f"    Title: {ptitle}")
        # Full event description can be important for resolution details,
        # so do not truncate it.
        desc = poly_event.get("description")
        if desc:
            lines.append(f"    Description: {desc}")
        res_src = poly_event.get("resolutionSource")
        if res_src:
            lines.append(f"    Resolution source: {res_src}")

    lines.append(f"    Markets: {len(poly_markets)}")
    if poly_markets:
        lines.append("    Markets (no prices):")
        for m in poly_markets:
            mid = m.get("id")
            q = _trunc(m.get("question"))
            summary_line = f"      {mid}: {q}..." if q else f"      {mid}"
            lines.append(summary_line)

            # Do NOT truncate Polymarket market descriptions; they often contain
            # crucial resolution criteria.
            mdesc = m.get("description")
            if mdesc:
                lines.append(f"        Description: {mdesc}")

            # Show timing with explicit labels so it's clear what the timestamp
            # refers to (end of market vs start of underlying event).
            end_date = m.get("endDate")
            event_start = m.get("eventStartTime")
            if end_date:
                lines.append(f"        Timing: endDate={end_date}")
            if event_start and event_start != end_date:
                lines.append(f"        Timing: eventStartTime={event_start}")

    description_block = "\n".join(lines)

    instructions = (
        "You are an expert in prediction markets and event interpretation across "
        "exchanges (Kalshi and Polymarket).\n\n"
        "Above, you see a pair of events (one from each platform) and summaries "
        "of their active markets, described without any prices. Focus only on "
        "the semantics of the events and markets (titles/questions, rules, "
        "resolution conditions, and timing).\n\n"
        "Your job is to decide whether there exist markets across these two "
        "events that *could* form an arbitrage opportunity if the prices were "
        "favorable. In other words, you are checking for structural/semantic "
        "compatibility, not current profitability.\n\n"
        "Respond ONLY in the following JSON format (and nothing else):\n\n"
        "{\n"
        "  \"could_have_arbitrage\": true | false,\n"
        "  \"reasons\": \"<short natural-language explanation>\",\n"
        "  \"matched_market_pairs\": [\n"
        "    {\n"
        "      \"kalshi_market_ticker\": \"<kalshi market ticker or null>\",\n"
        "      \"polymarket_market_id\": \"<polymarket market id/slug or null>\",\n"
        "      \"relationship\": \"same_outcome|inverse|compound|other\",\n"
        "      \"notes\": \"<any important caveats about resolution differences>\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )

    return instructions + "\n\n" + description_block


def build_prompts_for_top_candidates(
    csv_path: Optional[str] = None,
    min_similarity: float = 0.7,
    max_pairs: int = 20,
) -> List[Dict[str, Any]]:
    """Convenience helper: load candidates and build prompts for the top ones.

    Returns a list of dicts, each containing:
    - "candidate": the lightweight CSV row data
    - "pair_payload": full events+markets payload
    - "prompt": the final LLM-ready prompt string
    """
    candidates = load_cross_platform_candidates(
        csv_path=csv_path, min_similarity=min_similarity, max_rows=max_pairs
    )
    if not candidates:
        return []

    idxs = _build_event_indexes()
    kalshi_by_ticker = idxs["kalshi_by_ticker"]
    poly_by_id = idxs["polymarket_by_id"]

    results: List[Dict[str, Any]] = []
    for cand in candidates:
        pair_payload = build_event_pair_payload(cand, kalshi_by_ticker, poly_by_id)
        prompt = build_structured_prompt_for_pair(pair_payload)
        results.append(
            {
                "candidate": cand,
                "pair_payload": pair_payload,
                "prompt": prompt,
            }
        )

    return results


def save_prompts_to_csv(
    prompts_with_payloads: List[Dict[str, Any]],
    csv_path: str = "data/cross_platform_event_prompts.csv",
) -> None:
    """
    Persist the event/market pairs and their prompts to a CSV file.

    Each row corresponds to one Kalshi–Polymarket event pair and contains:
    - kalshi_ticker
    - polymarket_id
    - similarity
    - kalshi_title
    - polymarket_title
    - kalshi_markets_count
    - polymarket_markets_count
    - prompt (full prompt text)
    """
    if not prompts_with_payloads:
        return

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    fieldnames = [
        "kalshi_ticker",
        "polymarket_id",
        "similarity",
        "kalshi_title",
        "polymarket_title",
        "kalshi_markets_count",
        "polymarket_markets_count",
        "prompt",
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for item in prompts_with_payloads:
            cand = item.get("candidate", {}) or {}
            payload = item.get("pair_payload", {}) or {}

            kalshi_markets = payload.get("kalshi_markets") or []
            poly_markets = payload.get("polymarket_markets") or []

            writer.writerow(
                {
                    "kalshi_ticker": cand.get("kalshi_ticker"),
                    "polymarket_id": cand.get("polymarket_id"),
                    "similarity": cand.get("similarity"),
                    "kalshi_title": cand.get("kalshi_title"),
                    "polymarket_title": cand.get("polymarket_title"),
                    "kalshi_markets_count": len(kalshi_markets),
                    "polymarket_markets_count": len(poly_markets),
                    "prompt": item.get("prompt"),
                }
            )


if __name__ == "__main__":
    # Simple manual run: build prompts for the top-N most similar pairs
    # (above a similarity threshold) and print them.
    min_sim = 0.7
    max_pairs = 50

    prompts = build_prompts_for_top_candidates(
        csv_path=CROSS_PLATFORM_CANDIDATES_CSV,
        min_similarity=min_sim,
        max_pairs=max_pairs,
    )

    # Persist prompts plus basic pair metadata for downstream inspection / labeling.
    save_prompts_to_csv(prompts)

    print(
        f"Built {len(prompts)} prompts for cross-platform event pairs "
        f"(min_similarity={min_sim}, max_pairs={max_pairs})."
    )
    for i, item in enumerate(prompts, 1):
        cand = item["candidate"]
        print("\n" + "=" * 80)
        print(
            f"PAIR {i}: kalshi_ticker={cand.get('kalshi_ticker')} | "
            f"polymarket_id={cand.get('polymarket_id')} | "
            f"similarity={cand.get('similarity')}"
        )
        print("-" * 80)
        print(item["prompt"])
