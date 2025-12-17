import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from tqdm import tqdm

# Handle both package import and direct execution
try:
    # When run with project root on PYTHONPATH (e.g. `python -m arbitrage_finding.arbitrage_poly_kalshi`)
    from tools.emb import embed_texts, embed_text
    from tools.kalshi_events import (
        _load_events_and_embeddings as load_kalshi_events_and_embeddings,
    )
    from tools.kalshi_client import get_kalshi_client
    from tools.kalshi_markets import get_markets_for_event as get_kalshi_markets
    from tools.polymarket import (
        _load_events_and_embeddings as load_polymarket_events_and_embeddings,
    )
    from tools.polymarket import get_markets_for_event as get_polymarket_markets
except ImportError:
    # When run directly as a script, ensure the project root (parent of this file)
    # is on sys.path so the `tools` package can be imported.
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.emb import embed_texts, embed_text
    from tools.kalshi_events import (
        _load_events_and_embeddings as load_kalshi_events_and_embeddings,
    )
    from tools.kalshi_client import get_kalshi_client
    from tools.kalshi_markets import get_markets_for_event as get_kalshi_markets
    from tools.polymarket import (
        _load_events_and_embeddings as load_polymarket_events_and_embeddings,
    )
    from tools.polymarket import get_markets_for_event as get_polymarket_markets


# Default location where we persist cross-platform event candidates
CROSS_PLATFORM_CANDIDATES_CSV = "data/cross_platform_event_candidates.csv"
# To avoid huge CSVs and long write times, cap how many candidates we save.
CROSS_PLATFORM_CANDIDATES_MAX_ROWS = 5000


def _save_all_candidates_to_csv(
    candidates: List[Dict[str, Any]],
    csv_path: str = CROSS_PLATFORM_CANDIDATES_CSV,
) -> None:
    """
    Persist the (capped) set of cross-platform event candidates to a CSV file.

    This is intended for downstream evaluation / LLM inspection. We only need
    light metadata here; the full event payloads can be reloaded later using
    their identifiers (ticker / id).
    """
    if not candidates:
        return

    # Keep only the top-N most similar candidates to avoid enormous CSVs.
    # The list is expected to be pre-sorted by similarity (descending).
    candidates = candidates[:CROSS_PLATFORM_CANDIDATES_MAX_ROWS]

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    fieldnames = [
        "kalshi_ticker",
        "polymarket_id",
        "similarity",
        "kalshi_title",
        "kalshi_sub_title",
        "kalshi_category",
        "polymarket_title",
        "polymarket_category",
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for c in candidates:
            kalshi_event = c.get("kalshi_event", {}) or {}
            poly_event = c.get("polymarket_event", {}) or {}

            writer.writerow(
                {
                    "kalshi_ticker": c.get("kalshi_ticker"),
                    "polymarket_id": c.get("polymarket_id"),
                    "similarity": c.get("similarity"),
                    "kalshi_title": kalshi_event.get("title"),
                    "kalshi_sub_title": kalshi_event.get("sub_title"),
                    "kalshi_category": kalshi_event.get("category"),
                    "polymarket_title": poly_event.get("title"),
                    "polymarket_category": poly_event.get("category"),
                }
            )

def find_similar_cross_platform_events(
    top_k: int = 10,
    min_similarity: float = 0.0,
    exclude_exact_duplicates: bool = False,
) -> List[Dict[str, Any]]:
    """
    Find the most similar pairs of events between Polymarket and Kalshi by comparing their embeddings.
    
    Uses numpy for efficient vectorized cosine similarity computation.
    
    Args:
        top_k: Number of most similar pairs to return.
        min_similarity: Minimum cosine similarity threshold (0.0 to 1.0).
        exclude_exact_duplicates: If True, exclude pairs with similarity exactly 1.0
                                 (likely exact duplicates).
    
    Returns:
        List of dicts, each containing:
        - kalshi_event: Kalshi event dict
        - polymarket_event: Polymarket event dict
        - similarity: Cosine similarity score
        - kalshi_ticker: Ticker of Kalshi event
        - polymarket_id: ID/ticker/slug of Polymarket event
        - platform1: "kalshi"
        - platform2: "polymarket"
    """
    # Load events and embeddings from both platforms
    print("Loading Kalshi events and embeddings...")
    kalshi_events, kalshi_embeds = load_kalshi_events_and_embeddings()
    
    print("Loading Polymarket events and embeddings...")
    polymarket_events, polymarket_embeds = load_polymarket_events_and_embeddings()
    
    if len(kalshi_events) == 0 or len(polymarket_events) == 0:
        print("Not enough events from one or both platforms.")
        return []
    
    # Get Kalshi event tickers and their embeddings
    kalshi_tickers = []
    kalshi_embeddings_list = []
    kalshi_indices = []
    
    for i, ev in enumerate(kalshi_events):
        ticker = ev.get("event_ticker") or ev.get("series_ticker")
        if ticker and ticker in kalshi_embeds:
            kalshi_tickers.append(ticker)
            kalshi_embeddings_list.append(kalshi_embeds[ticker])
            kalshi_indices.append(i)
    
    # Get Polymarket event identifiers and their embeddings
    polymarket_ids = []
    polymarket_embeddings_list = []
    polymarket_indices = []
    
    for i, ev in enumerate(polymarket_events):
        event_id = ev.get("id") or ev.get("ticker") or ev.get("slug")
        if event_id and str(event_id) in polymarket_embeds:
            polymarket_ids.append(str(event_id))
            polymarket_embeddings_list.append(polymarket_embeds[str(event_id)])
            polymarket_indices.append(i)
    
    if len(kalshi_embeddings_list) == 0 or len(polymarket_embeddings_list) == 0:
        print("Not enough events with embeddings to compare.")
        return []
    
    # Convert to numpy arrays for efficient computation
    kalshi_embeddings_array = np.array(kalshi_embeddings_list, dtype=np.float32)
    polymarket_embeddings_array = np.array(polymarket_embeddings_list, dtype=np.float32)
    
    n_kalshi = len(kalshi_embeddings_array)
    n_polymarket = len(polymarket_embeddings_array)
    
    print(f"Comparing {n_kalshi} Kalshi events with {n_polymarket} Polymarket events ({n_kalshi * n_polymarket:,} pairs)...")
    
    # Normalize embeddings (L2 norm) for efficient cosine similarity
    kalshi_norms = np.linalg.norm(kalshi_embeddings_array, axis=1, keepdims=True)
    kalshi_norms[kalshi_norms == 0] = 1
    kalshi_normalized = kalshi_embeddings_array / kalshi_norms
    
    polymarket_norms = np.linalg.norm(polymarket_embeddings_array, axis=1, keepdims=True)
    polymarket_norms[polymarket_norms == 0] = 1
    polymarket_normalized = polymarket_embeddings_array / polymarket_norms
    
    # Compute all pairwise cosine similarities using matrix multiplication
    # similarity_matrix[i, j] = cosine_sim(kalshi[i], polymarket[j])
    similarity_matrix = np.dot(kalshi_normalized, polymarket_normalized.T)
    
    # Collect all candidates above threshold
    all_candidates: List[Dict[str, Any]] = []
    
    total_pairs = n_kalshi * n_polymarket
    with tqdm(total=total_pairs, desc="Comparing cross-platform event pairs", unit="pairs") as pbar:
        for i in range(n_kalshi):
            for j in range(n_polymarket):
                sim = float(similarity_matrix[i, j])
                if sim >= min_similarity:
                    # Skip exact duplicates if requested
                    if exclude_exact_duplicates and sim >= 0.9999:
                        pbar.update(1)
                        continue
                    
                    kalshi_event = kalshi_events[kalshi_indices[i]]
                    polymarket_event = polymarket_events[polymarket_indices[j]]
                    kalshi_ticker = kalshi_tickers[i]
                    polymarket_id = polymarket_ids[j]
                    
                    all_candidates.append({
                        "kalshi_event": kalshi_event,
                        "polymarket_event": polymarket_event,
                        "similarity": sim,
                        "kalshi_ticker": kalshi_ticker,
                        "polymarket_id": polymarket_id,
                        "platform1": "kalshi",
                        "platform2": "polymarket",
                    })
                pbar.update(1)
    
    # Sort by similarity (highest first)
    all_candidates.sort(key=lambda x: x["similarity"], reverse=True)

    # Persist *all* candidates for downstream evaluation / LLM inspection
    _save_all_candidates_to_csv(all_candidates)
    
    # Return only the requested top_k subset to callers
    return all_candidates[:top_k]


def find_arbitrage_opportunities_cross_platform(
    top_k_events: int = 10,
    min_event_similarity: float = 0.7,
    exclude_exact_duplicates: bool = True,
) -> List[Dict[str, Any]]:
    """
    Find potential arbitrage opportunities by:
    1. Finding similar events between Polymarket and Kalshi using embeddings
    2. For each pair of similar events, fetching their markets from both platforms
    
    Args:
        top_k_events: Number of most similar event pairs to analyze.
        min_event_similarity: Minimum cosine similarity threshold for events (default 0.7).
        exclude_exact_duplicates: If True, exclude pairs with similarity exactly 1.0
                                  (likely exact duplicates). Default True.
    
    Returns:
        List of dicts containing similar event pairs with their markets, each with:
        - kalshi_event: Kalshi event dict
        - polymarket_event: Polymarket event dict
        - event_similarity: Similarity between the two events
        - kalshi_ticker: Ticker of Kalshi event
        - polymarket_id: ID/ticker/slug of Polymarket event
        - kalshi_markets: List of markets for Kalshi event
        - polymarket_markets: List of markets for Polymarket event
        - platform1: "kalshi"
        - platform2: "polymarket"
    """
    # Step 1: Find similar events across platforms
    print(f"Finding similar events across platforms (min similarity: {min_event_similarity})...")
    similar_events = find_similar_cross_platform_events(
        top_k=top_k_events,
        min_similarity=min_event_similarity,
        exclude_exact_duplicates=exclude_exact_duplicates,
    )
    
    if not similar_events:
        print("No similar events found across platforms.")
        return []
    
    print(f"Found {len(similar_events)} similar event pairs. Fetching markets...")
    
    # Step 2: For each pair of similar events, fetch their markets
    results = []
    for pair in tqdm(similar_events, desc="Fetching markets for cross-platform event pairs", unit="pair"):
        kalshi_ticker = pair["kalshi_ticker"]
        polymarket_id = pair["polymarket_id"]
        polymarket_event = pair["polymarket_event"]
        
        # Fetch markets for both events
        kalshi_markets = get_kalshi_markets(kalshi_ticker)
        # For Polymarket, use the event dict directly if available (more efficient)
        polymarket_markets = get_polymarket_markets(event_dict=polymarket_event)
        
        # If no markets from event dict, try fetching by ID
        if not polymarket_markets:
            polymarket_markets = get_polymarket_markets(event_id=polymarket_id)
        
        results.append({
            "kalshi_event": pair["kalshi_event"],
            "polymarket_event": pair["polymarket_event"],
            "event_similarity": pair["similarity"],
            "kalshi_ticker": kalshi_ticker,
            "polymarket_id": polymarket_id,
            "kalshi_markets": kalshi_markets,
            "polymarket_markets": polymarket_markets,
            "platform1": "kalshi",
            "platform2": "polymarket",
        })
    
    return results


if __name__ == "__main__":
    # Example usage
    print("Finding cross-platform arbitrage opportunities (Polymarket <-> Kalshi)...")
    
    results = find_arbitrage_opportunities_cross_platform(
        top_k_events=50,
        min_event_similarity=0.7,
        exclude_exact_duplicates=False,
    )
    
    print(f"\nFound {len(results)} similar event pairs across platforms:\n")
    for i, result in enumerate(results, 1):
        print(f"Event Pair {i}:")
        print(f"  Event Similarity: {result['event_similarity']:.4f}")
        print(f"  Kalshi Event: {result['kalshi_ticker']}")
        print(f"    Title: {result['kalshi_event'].get('title', 'N/A')}")
        print(f"    Markets: {len(result['kalshi_markets'])}")
        if result['kalshi_markets']:
            print(f"    Market prices:")
            for market in result['kalshi_markets'][:3]:  # Show first 3 markets
                ticker = market.get('ticker', 'unknown')
                title = market.get('title', 'N/A')
                yes_ask = market.get('yes_ask')
                no_ask = market.get('no_ask')
                print(f"      {ticker}: {title[:60]}...")
                print(f"        YES ask: {yes_ask}, NO ask: {no_ask}")
        print(f"  Polymarket Event: {result['polymarket_id']}")
        print(f"    Title: {result['polymarket_event'].get('title', 'N/A')}")
        print(f"    Markets: {len(result['polymarket_markets'])}")
        if result['polymarket_markets']:
            print(f"    Market prices:")
            for market in result['polymarket_markets'][:3]:  # Show first 3 markets
                market_id = market.get('id', market.get('slug', 'unknown'))
                question = market.get('question', 'N/A')
                # Polymarket bestBid and bestAsk are for the "Yes" side
                best_bid = market.get('bestBid')
                best_ask = market.get('bestAsk')
                # Yes price = bestAsk (what you pay to buy Yes)
                # No price = 1 - bestBid (what you pay to buy No)
                yes_price = float(best_ask) if best_ask is not None else None
                no_price = 1.0 - float(best_bid) if best_bid is not None else None
                print(f"      {market_id}: {question[:60]}...")
                print(f"        YES price: {yes_price}, NO price: {no_price}")
        print()