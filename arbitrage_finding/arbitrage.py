"""
DEPRECATED: Use arbitrage_poly_kalshi.py instead.
"""
import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

from tools.emb import embed_texts, embed_text
from tools.kalshi_events import _load_events_and_embeddings, fetch_all_open_events
from tools.kalshi_markets import get_markets_for_event


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


def _should_filter_event_pair(event1_ticker: str, event2_ticker: str) -> bool:
    """
    Filter out event pairs that are not useful for arbitrage:
    - Events that only differ by date/time (e.g., KXEURUSDH-25DEC1014 vs KXEURUSDH-25DEC1013)
    - Events from different sports/leagues (e.g., KXNBA vs KXNFL)
    - Events that are the same instrument but different timeframes (e.g., KXUSDJPY vs KXUSDJPYH)
    
    Returns True if the pair should be filtered out (excluded).
    """
    # Filter 1: Date/time-only differences
    # Extract base ticker (everything before the date/time part)
    # Pattern: KXEURUSDH-25DEC1014 -> base is KXEURUSDH, date is 25DEC1014
    # We want to detect when two events have the same base but different dates
    
    # Normalize tickers by removing optional suffixes like 'H' (hourly) before comparing
    # This handles cases like KXUSDJPY vs KXUSDJPYH
    def normalize_base(ticker: str) -> str:
        # Remove date patterns first
        base = re.sub(r'-\d+[A-Z]+\d+$', '', ticker)  # Remove -25DEC1014 style
        base = re.sub(r'-\d+$', '', base)  # Remove trailing -26 style
        # Then remove common timeframe suffixes (H for hourly, etc.)
        base = re.sub(r'[A-Z]$', '', base)  # Remove single letter suffix like H
        return base
    
    base1 = normalize_base(event1_ticker)
    base2 = normalize_base(event2_ticker)
    
    # If normalized bases are the same but full tickers differ, check if it's just date/time
    if base1 == base2 and event1_ticker != event2_ticker:
        # Extract date parts from both tickers
        date_match1 = re.search(r'-(\d+[A-Z]+\d+)$', event1_ticker)
        date_match2 = re.search(r'-(\d+[A-Z]+\d+)$', event2_ticker)
        
        # If both have dates and dates are different, filter out
        # This catches: KXUSDJPY-25DEC1010 vs KXUSDJPYH-25DEC1009
        if date_match1 and date_match2:
            date1 = date_match1.group(1)
            date2 = date_match2.group(1)
            if date1 != date2:
                return True
    
    # Filter 2: Different sports/leagues (NBA vs NFL, etc.)
    # Check for known league prefixes
    league_prefixes = {
        'KXNBA': 'basketball',
        'KXNFL': 'football',
        'KXNCAA': 'college',
        'KXMBL': 'baseball',
        'KXNHL': 'hockey',
    }
    
    league1 = None
    league2 = None
    
    for prefix, league in league_prefixes.items():
        if event1_ticker.startswith(prefix):
            league1 = league
        if event2_ticker.startswith(prefix):
            league2 = league
    
    # If both have leagues and they're different, filter out
    if league1 and league2 and league1 != league2:
        return True
    
    return False


def find_similar_events(
    top_k: int = 10,
    min_similarity: float = 0.0,
    exclude_exact_duplicates: bool = False,
    oversample_factor: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Find the most similar pairs of events by comparing their embeddings.
    
    Uses numpy for efficient vectorized cosine similarity computation.
    
    Args:
        top_k: Number of most similar pairs to return (after filtering).
        min_similarity: Minimum cosine similarity threshold (0.0 to 1.0).
        exclude_exact_duplicates: If True, exclude pairs with similarity exactly 1.0
                                 (likely exact duplicates).
        oversample_factor: Factor to oversample before filtering to ensure we get
                          enough results after filtering (default 2.0).
    
    Returns:
        List of dicts, each containing:
        - event1: First event dict
        - event2: Second event dict
        - similarity: Cosine similarity score
        - event1_ticker: Ticker of first event
        - event2_ticker: Ticker of second event
    """
    # Load events and their embeddings
    events, embeds = _load_events_and_embeddings()
    
    if len(events) < 2:
        return []
    
    # Get event tickers and their embeddings
    event_tickers = []
    event_embeddings_list = []
    event_indices = []
    
    for i, ev in enumerate(events):
        ticker = ev.get("event_ticker") or ev.get("series_ticker")
        if ticker and ticker in embeds:
            event_tickers.append(ticker)
            event_embeddings_list.append(embeds[ticker])
            event_indices.append(i)
    
    if len(event_embeddings_list) < 2:
        print("Not enough events with embeddings to compare.")
        return []
    
    # Convert to numpy array for efficient computation
    # Shape: (n_events, embedding_dim)
    embeddings_array = np.array(event_embeddings_list, dtype=np.float32)
    n_events = len(embeddings_array)
    
    print(f"Comparing {n_events} event embeddings ({n_events * (n_events - 1) // 2:,} pairs)...")
    
    # Normalize embeddings (L2 norm) for efficient cosine similarity
    # Cosine similarity = dot product of normalized vectors
    norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Avoid division by zero
    embeddings_normalized = embeddings_array / norms
    
    # Compute all pairwise cosine similarities using matrix multiplication
    # This is much faster than nested loops
    # similarity_matrix[i, j] = cosine_sim(embeddings[i], embeddings[j])
    similarity_matrix = np.dot(embeddings_normalized, embeddings_normalized.T)
    
    # Extract upper triangle (avoid duplicates and self-comparisons)
    # and find pairs above threshold
    # We collect candidates first, then filter, to ensure we can get top_k after filtering
    all_candidates: List[Dict[str, Any]] = []
    
    total_pairs = n_events * (n_events - 1) // 2
    with tqdm(total=total_pairs, desc="Comparing event pairs", unit="pairs") as pbar:
        for i in range(n_events):
            for j in range(i + 1, n_events):
                sim = float(similarity_matrix[i, j])
                if sim >= min_similarity:
                    # Skip exact duplicates if requested
                    if exclude_exact_duplicates and sim >= 0.9999:  # Use 0.9999 to account for floating point precision
                        pbar.update(1)
                        continue
                    
                    event1 = events[event_indices[i]]
                    event2 = events[event_indices[j]]
                    event1_ticker = event_tickers[i]
                    event2_ticker = event_tickers[j]
                    
                    all_candidates.append({
                        "event1": event1,
                        "event2": event2,
                        "similarity": sim,
                        "event1_ticker": event1_ticker,
                        "event2_ticker": event2_ticker,
                    })
                pbar.update(1)
    
    # Sort by similarity (highest first) before filtering
    all_candidates.sort(key=lambda x: x["similarity"], reverse=True)
    
    # Now filter out unwanted pairs, keeping top candidates first
    filtered_similarities: List[Dict[str, Any]] = []
    for candidate in all_candidates:
        # Filter out pairs that are not useful for arbitrage
        if _should_filter_event_pair(candidate["event1_ticker"], candidate["event2_ticker"]):
            continue
        
        filtered_similarities.append(candidate)
        
        # Stop once we have enough after filtering
        if len(filtered_similarities) >= top_k:
            break
    
    # Return top_k after filtering (may be fewer if not enough candidates passed filters)
    return filtered_similarities[:top_k]


def find_arbitrage_opportunities(
    top_k_events: int = 10,
    min_event_similarity: float = 0.7,
    exclude_exact_duplicates: bool = True,
) -> List[Dict[str, Any]]:
    """
    Find potential arbitrage opportunities by:
    1. Finding similar events using embeddings
    2. For each pair of similar events, fetching their markets
    
    Args:
        top_k_events: Number of most similar event pairs to analyze.
        min_event_similarity: Minimum cosine similarity threshold for events (default 0.7).
        exclude_exact_duplicates: If True, exclude pairs with similarity exactly 1.0
                                  (likely exact duplicates). Default True.
    
    Returns:
        List of dicts containing similar event pairs with their markets, each with:
        - event1: First event dict
        - event2: Second event dict
        - event_similarity: Similarity between the two events
        - event1_ticker: Ticker of first event
        - event2_ticker: Ticker of second event
        - markets1: List of markets for event1
        - markets2: List of markets for event2
    """
    # Step 1: Find similar events
    print(f"Finding similar events (min similarity: {min_event_similarity})...")
    similar_events = find_similar_events(
        top_k=top_k_events,
        min_similarity=min_event_similarity,
        exclude_exact_duplicates=exclude_exact_duplicates,
    )
    
    if not similar_events:
        print("No similar events found.")
        return []
    
    print(f"Found {len(similar_events)} similar event pairs. Fetching markets...")
    
    # Step 2: For each pair of similar events, fetch their markets
    results = []
    for pair in tqdm(similar_events, desc="Fetching markets for event pairs", unit="pair"):
        event1_ticker = pair["event1_ticker"]
        event2_ticker = pair["event2_ticker"]
        
        # Fetch markets for both events
        markets1 = get_markets_for_event(event1_ticker)
        markets2 = get_markets_for_event(event2_ticker)
        
        results.append({
            "event1": pair["event1"],
            "event2": pair["event2"],
            "event_similarity": pair["similarity"],
            "event1_ticker": event1_ticker,
            "event2_ticker": event2_ticker,
            "markets1": markets1,
            "markets2": markets2,
        })
    
    return results


if __name__ == "__main__":
    # Example usage
    print("Finding arbitrage opportunities by comparing similar events...")
    
    results = find_arbitrage_opportunities(
        top_k_events=50,
        min_event_similarity=0.7,
        exclude_exact_duplicates=False,
    )
    
    print(f"\nFound {len(results)} similar event pairs:\n")
    for i, result in enumerate(results, 1):
        print(f"Event Pair {i}:")
        print(f"  Event Similarity: {result['event_similarity']:.4f}")
        print(f"  Event 1: {result['event1_ticker']}")
        print(f"    Title: {result['event1'].get('title', 'N/A')}")
        print(f"    Markets: {len(result['markets1'])}")
        if result['markets1']:
            print(f"    Market prices:")
            for market in result['markets1']:
                ticker = market.get('ticker', 'unknown')
                title = market.get('title', 'N/A')
                yes_ask = market.get('yes_ask')
                no_ask = market.get('no_ask')
                print(f"      {ticker}: {title}")
                print(f"        YES ask: {yes_ask}, NO ask: {no_ask}")
        print(f"  Event 2: {result['event2_ticker']}")
        print(f"    Title: {result['event2'].get('title', 'N/A')}")
        print(f"    Markets: {len(result['markets2'])}")
        if result['markets2']:
            print(f"    Market prices:")
            for market in result['markets2']:
                ticker = market.get('ticker', 'unknown')
                title = market.get('title', 'N/A')
                yes_ask = market.get('yes_ask')
                no_ask = market.get('no_ask')
                print(f"      {ticker}: {title}")
                print(f"        YES ask: {yes_ask}, NO ask: {no_ask}")
        print()

