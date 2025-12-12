#!/usr/bin/env python3
"""
Script to check for arbitrage opportunities between Kalshi and Polymarket markets.

This script:
1. Loads event pairs that have potential arbitrage from a CSV file
2. For each matched market pair, checks if there's an actual arbitrage opportunity
3. Calculates profits including trading fees (Kalshi has fees, Polymarket does not)
4. Saves results to a CSV file and displays summary statistics
"""

import pandas as pd
import sys
import math
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.markets import get_markets_for_event as get_kalshi_markets
from tools.polymarket import get_markets_for_event as get_polymarket_markets

# Trading fee rate for Kalshi (7% = 0.07)
# Note: Polymarket has NO trading fees
KALSHI_FEE_RATE = 0.07


def calculate_kalshi_trading_fee(price, contracts=1):
    """
    Calculate trading fee for Kalshi trades only.
    
    Formula: fees = round_up(0.07 x C x P x (1-P))
    - P = price of contract in dollars (0.5 for 50 cents)
    - C = number of contracts
    - 0.07 = 7% fee rate
    
    Note: Polymarket has NO trading fees, so this function is only for Kalshi.
    
    Args:
        price: Price of contract in dollars (0.0 to 1.0)
        contracts: Number of contracts (default 1 for per-$1 calculation)
    
    Returns:
        Fee in dollars
    """
    if price <= 0 or price >= 1:
        return 0.0
    
    fee = KALSHI_FEE_RATE * contracts * price * (1 - price)
    # Round up to next cent
    return math.ceil(fee * 100) / 100.0


def get_polymarket_prices(market):
    """
    Extract YES and NO prices from a Polymarket market.
    
    Polymarket pricing:
    - YES price = bestAsk (what you pay to buy Yes)
    - NO price = 1 - bestBid (what you pay to buy No)
    """
    try:
        best_bid = market.get('bestBid')
        best_ask = market.get('bestAsk')
        
        yes_price = None
        no_price = None
        
        if best_ask is not None:
            yes_price = float(best_ask)
            # Validate price is in valid range
            if yes_price < 0 or yes_price > 1:
                yes_price = None
        
        if best_bid is not None:
            bid_val = float(best_bid)
            # Validate bid is in valid range
            if 0 <= bid_val <= 1:
                no_price = 1.0 - bid_val
                # Validate no_price is in valid range
                if no_price < 0 or no_price > 1:
                    no_price = None
        
        return yes_price, no_price
    except (ValueError, TypeError) as e:
        return None, None


def get_kalshi_prices(market):
    """
    Extract YES and NO prices from a Kalshi market.
    
    Kalshi pricing:
    - YES price = yes_ask (in cents, convert to decimal)
    - NO price = no_ask (in cents, convert to decimal)
    """
    try:
        yes_ask = market.get('yes_ask')
        no_ask = market.get('no_ask')
        
        yes_price = None
        no_price = None
        
        if yes_ask is not None:
            yes_price = float(yes_ask) / 100.0
            # Validate price is in valid range
            if yes_price < 0 or yes_price > 1:
                yes_price = None
        
        if no_ask is not None:
            no_price = float(no_ask) / 100.0
            # Validate price is in valid range
            if no_price < 0 or no_price > 1:
                no_price = None
        
        return yes_price, no_price
    except (ValueError, TypeError) as e:
        return None, None


def parse_matched_market_pairs(matched_pairs_json: str) -> List[Dict[str, Any]]:
    """
    Parse the matched_market_pairs_json string into a list of matched pairs.
    
    Format example:
    [
        {
            "kalshi_market_ticker": "KXNFLNFCEAST-25-PHI",
            "polymarket_market_id": "540286",
            "relationship": "same_outcome",
            "notes": "..."
        },
        ...
    ]
    
    IMPORTANT: An event may have many markets (e.g., 11 Kalshi markets, 4 Polymarket markets),
    but only SOME of those markets are matched (e.g., only 3 matched pairs in the JSON).
    We only check arbitrage for the matched pairs, not all combinations.
    
    Args:
        matched_pairs_json: JSON string containing matched market pairs
        
    Returns:
        List of dicts with 'kalshi_market_ticker' and 'polymarket_market_id' (or similar)
    """
    if not matched_pairs_json or pd.isna(matched_pairs_json) or matched_pairs_json.strip() == "":
        return []
    
    try:
        pairs = json.loads(matched_pairs_json)
        if isinstance(pairs, list):
            return pairs
        return []
    except (json.JSONDecodeError, TypeError) as e:
        print(f"Error parsing matched_market_pairs_json: {e}")
        return []


def find_market_by_ticker(markets: List[Dict[str, Any]], ticker: str) -> Optional[Dict[str, Any]]:
    """Find a Kalshi market by its ticker."""
    for market in markets:
        if market.get('ticker') == ticker:
            return market
    return None


def find_market_by_id(markets: List[Dict[str, Any]], market_id: Any) -> Optional[Dict[str, Any]]:
    """Find a Polymarket market by its ID."""
    # Try different possible ID fields
    market_id_str = str(market_id)
    for market in markets:
        # Check various ID fields
        if (str(market.get('id', '')) == market_id_str or
            str(market.get('market_id', '')) == market_id_str or
            str(market.get('slug', '')) == market_id_str):
            return market
    return None


def check_arbitrage_opportunity(
    kalshi_markets: List[Dict[str, Any]],
    polymarket_markets: List[Dict[str, Any]],
    matched_pairs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Check for arbitrage opportunities between matched Kalshi and Polymarket markets.
    
    Only checks markets that are in the matched_pairs list (markets that represent
    the same underlying question/outcome).
    
    Fee structure:
    - Polymarket: NO trading fees (fee = $0.00)
    - Kalshi: Fee = round_up(0.07 x C x P x (1-P))
      (Only charged on immediately matched orders - market orders)
    
    Arbitrage exists if: (poly_price + poly_fee) + (kalshi_price + kalshi_fee) < 1.0
    Since poly_fee = 0, this simplifies to: poly_price + (kalshi_price + kalshi_fee) < 1.0
    
    Args:
        kalshi_markets: List of all Kalshi markets for the event
        polymarket_markets: List of all Polymarket markets for the event
        matched_pairs: List of matched market pairs from JSON (each with kalshi_market_ticker and polymarket_market_id)
    
    Returns:
        List of arbitrage opportunities with details.
    """
    opportunities = []
    
    # Only check matched pairs, not all combinations
    # Note: An event may have many markets (e.g., 11 Kalshi markets, 4 Polymarket markets)
    # But we only check the markets that are in matched_pairs (e.g., 3 matched pairs)
    print(f"  Checking {len(matched_pairs)} matched market pair(s) for arbitrage...")
    print(f"  (Event has {len(kalshi_markets)} total Kalshi markets, {len(polymarket_markets)} total Polymarket markets)")
    
    for pair_idx, pair in enumerate(matched_pairs, 1):
        # Parse the matched pair - JSON format: {"kalshi_market_ticker": "...", "polymarket_market_id": "..."}
        kalshi_ticker = pair.get('kalshi_market_ticker')
        # Try different possible field names for Polymarket market ID
        polymarket_id = pair.get('polymarket_market_id') or pair.get('polymarket_id') or pair.get('poly_market_id')
        
        print(f"  Matched pair #{pair_idx}: Kalshi ticker={kalshi_ticker}, Polymarket ID={polymarket_id}")
        
        if not kalshi_ticker or not polymarket_id:
            print(f"    ⚠️  Missing ticker or ID, skipping")
            continue
        
        # Find the specific markets from the full event markets list
        kalshi_market = find_market_by_ticker(kalshi_markets, kalshi_ticker)
        poly_market = find_market_by_id(polymarket_markets, polymarket_id)

        if not kalshi_market:
            print(f"    ⚠️  Kalshi market {kalshi_ticker} not found in event markets")
            print(f"       Available Kalshi market tickers: {[m.get('ticker') for m in kalshi_markets[:5]]}")
            continue
        
        if not poly_market:
            print(f"    ⚠️  Polymarket market {polymarket_id} not found in event markets")
            print(f"       Available Polymarket market IDs: {[m.get('id') for m in polymarket_markets[:5]]}")
            continue
        
        # Confirm we found the correct markets
        print(f"    ✓ Found Kalshi market: {kalshi_market.get('ticker')} - {kalshi_market.get('title', 'N/A')[:50]}")
        print(f"    ✓ Found Polymarket market: {poly_market.get('id')} - {poly_market.get('question', 'N/A')[:50]}")
        
        # Extract prices
        poly_yes, poly_no = get_polymarket_prices(poly_market)
        kalshi_yes, kalshi_no = get_kalshi_prices(kalshi_market)
        
        if poly_yes is None or poly_no is None:
            print(f"    ⚠️  Missing prices for Polymarket market {polymarket_id}")
            continue
        
        if kalshi_yes is None or kalshi_no is None:
            print(f"    ⚠️  Missing prices for Kalshi market {kalshi_ticker}")
            continue
        
        # Strategy 1: Buy YES on Polymarket, Buy NO on Kalshi
        poly_yes_fee = 0.0  # Polymarket has no fees
        kalshi_no_fee = calculate_kalshi_trading_fee(kalshi_no, contracts=1)
        
        combo1_total_cost = poly_yes + poly_yes_fee + kalshi_no + kalshi_no_fee
        combo1_profit = 1.0 - combo1_total_cost
        
        # Strategy 2: Buy NO on Polymarket, Buy YES on Kalshi
        poly_no_fee = 0.0  # Polymarket has no fees
        kalshi_yes_fee = calculate_kalshi_trading_fee(kalshi_yes, contracts=1)
        
        combo2_total_cost = poly_no + poly_no_fee + kalshi_yes + kalshi_yes_fee
        combo2_profit = 1.0 - combo2_total_cost
        
        # Check if either combination is profitable
        pair_has_opportunity = False
        
        if combo1_profit > 0:
            print(f"    ✅ Found arbitrage opportunity: Strategy 1 (Buy YES Poly + Buy NO Kalshi), Profit: {combo1_profit*100:.2f}%")
            pair_has_opportunity = True
            opportunities.append({
                'strategy': 'Buy YES on Polymarket, Buy NO on Kalshi',
                'poly_market_id': poly_market.get('id'),
                'poly_market_title': poly_market.get('question'),
                'kalshi_market_ticker': kalshi_market.get('ticker'),
                'kalshi_market_title': kalshi_market.get('title'),
                'poly_yes_price': poly_yes,
                'poly_yes_fee': poly_yes_fee,  # Always 0.0
                'kalshi_no_price': kalshi_no,
                'kalshi_no_fee': kalshi_no_fee,
                'total_cost': combo1_total_cost,
                'total_fees': poly_yes_fee + kalshi_no_fee,  # Only Kalshi fees
                'profit': combo1_profit,
                'profit_pct': combo1_profit * 100
            })
        
        if combo2_profit > 0:
            print(f"    ✅ Found arbitrage opportunity: Strategy 2 (Buy NO Poly + Buy YES Kalshi), Profit: {combo2_profit*100:.2f}%")
            pair_has_opportunity = True
            opportunities.append({
                'strategy': 'Buy NO on Polymarket, Buy YES on Kalshi',
                'poly_market_id': poly_market.get('id'),
                'poly_market_title': poly_market.get('question'),
                'kalshi_market_ticker': kalshi_market.get('ticker'),
                'kalshi_market_title': kalshi_market.get('title'),
                'poly_no_price': poly_no,
                'poly_no_fee': poly_no_fee,  # Always 0.0
                'kalshi_yes_price': kalshi_yes,
                'kalshi_yes_fee': kalshi_yes_fee,
                'total_cost': combo2_total_cost,
                'total_fees': poly_no_fee + kalshi_yes_fee,  # Only Kalshi fees
                'profit': combo2_profit,
                'profit_pct': combo2_profit * 100
            })
        
        if not pair_has_opportunity:
            print(f"    ❌ No arbitrage opportunity for this matched pair")
            print(f"      Strategy 1 (Buy YES Poly + Buy NO Kalshi):")
            print(f"        Poly YES price: ${poly_yes:.4f} (fee: $0.00)")
            print(f"        Kalshi NO price: ${kalshi_no:.4f} (fee: ${kalshi_no_fee:.4f})")
            print(f"        Total cost: ${combo1_total_cost:.4f}, Profit: ${combo1_profit:.4f} ({combo1_profit*100:.2f}%)")
            print(f"      Strategy 2 (Buy NO Poly + Buy YES Kalshi):")
            print(f"        Poly NO price: ${poly_no:.4f} (fee: $0.00)")
            print(f"        Kalshi YES price: ${kalshi_yes:.4f} (fee: ${kalshi_yes_fee:.4f})")
            print(f"        Total cost: ${combo2_total_cost:.4f}, Profit: ${combo2_profit:.4f} ({combo2_profit*100:.2f}%)")
            print(f"      Reason: Both strategies have total cost >= $1.00 (including fees), so no arbitrage exists")
    
    return opportunities


def main():
    """Main function to run the arbitrage check."""
    # Load the results CSV to get pairs that have arbitrage potential
    input_file = Path(__file__).parent.parent / "data" / "cross_platform_event_results.csv"
    df = pd.read_csv(input_file)
    arbitrage_possible = df[df["could_have_arbitrage"] == True]
    print(f"Found {len(arbitrage_possible)} event pairs with potential arbitrage")
    print(f"\nColumns: {arbitrage_possible.columns.tolist()}\n")
    
    # Process each event pair and check for arbitrage
    all_opportunities = []

    for idx, row in arbitrage_possible.iterrows():
        kalshi_ticker = row.get('kalshi_ticker')
        polymarket_id = row.get('polymarket_id')
        matched_pairs_json = row.get('matched_market_pairs_json', '')
        
        print(f"\n{'='*80}")
        print(f"Processing pair {idx + 1}/{len(arbitrage_possible)}")
        print(f"Kalshi Event: {kalshi_ticker}")
        print(f"Polymarket Event ID: {polymarket_id}")
        print(f"Similarity: {row.get('similarity', 'N/A')}")
        
        # Parse matched market pairs
        matched_pairs = parse_matched_market_pairs(matched_pairs_json)
        print(f"Found {len(matched_pairs)} matched market pair(s) in JSON")
        
        if not matched_pairs:
            print("⚠️  No matched market pairs found, skipping this event pair")
            continue
        
        # Get all Kalshi markets for the event (needed to find specific matched markets)
        try:
            kalshi_markets = get_kalshi_markets(kalshi_ticker)
        except Exception as e:
            print(f"Error fetching Kalshi markets: {e}")
            kalshi_markets = []
        
        # Get all Polymarket markets for the event (needed to find specific matched markets)
        try:
            polymarket_markets = get_polymarket_markets(event_id=str(polymarket_id))
        except Exception as e:
            print(f"Error fetching Polymarket markets: {e}")
            polymarket_markets = []
        
        # Check for arbitrage opportunities only for matched pairs
        if kalshi_markets and polymarket_markets:
            opportunities = check_arbitrage_opportunity(kalshi_markets, polymarket_markets, matched_pairs)
        
            if opportunities:
                print(f"✅ Found {len(opportunities)} arbitrage opportunity(ies) across {len(matched_pairs)} matched pair(s)!")
                for opp in opportunities:
                    opp['kalshi_event_ticker'] = kalshi_ticker
                    opp['polymarket_event_id'] = polymarket_id
                    all_opportunities.append(opp)
            else:
                print(f"❌ No arbitrage opportunities found for {len(matched_pairs)} matched pair(s)")
        else:
            print("⚠️  Missing market data, skipping")
    
    # Display all arbitrage opportunities found
    if all_opportunities:
        print(f"\n{'='*80}")
        print(f"SUMMARY: Found {len(all_opportunities)} total arbitrage opportunities from matched market pairs")
        print(f"{'='*80}\n")
        
        opportunities_df = pd.DataFrame(all_opportunities)
        
        # Sort by profit percentage (highest first)
        opportunities_df = opportunities_df.sort_values('profit_pct', ascending=False)

        # Display all opportunities
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 50)
        
        print(opportunities_df.to_string())
        
        # Save to CSV
        output_file = Path(__file__).parent.parent / "data" / "arbitrage_opportunities.csv"
        opportunities_df.to_csv(output_file, index=False)
        print(f"\n✅ Saved {len(all_opportunities)} opportunities to {output_file}")
        
        # Detailed view of top opportunities
        print("\n" + "="*80)
        print("TOP ARBITRAGE OPPORTUNITIES (by profit %)")
        print("="*80 + "\n")

        for idx, (_, row) in enumerate(opportunities_df.head(10).iterrows(), 1):
            print(f"\nOpportunity #{idx}")
            print(f"  Strategy: {row['strategy']}")
            print(f"  Profit: {row['profit_pct']:.2f}% (${row['profit']:.4f} per $1)")
            print(f"  Total Cost: ${row['total_cost']:.4f} (including fees)")
            print(f"  Total Fees: ${row['total_fees']:.4f}")
            print(f"  Kalshi Event: {row['kalshi_event_ticker']}")
            print(f"  Kalshi Market: {row['kalshi_market_ticker']}")
            print(f"  Kalshi Market Title: {row['kalshi_market_title']}")
            print(f"  Polymarket Event ID: {row['polymarket_event_id']}")
            print(f"  Polymarket Market ID: {row['poly_market_id']}")
            print(f"  Polymarket Market Title: {row['poly_market_title']}")
            
            # Show prices and fees based on strategy
            if 'poly_yes_price' in row and pd.notna(row['poly_yes_price']):
                print(f"  Polymarket YES Price: ${row['poly_yes_price']:.4f} (Fee: $0.00 - no fees on Polymarket)")
                print(f"  Kalshi NO Price: ${row['kalshi_no_price']:.4f} (Fee: ${row['kalshi_no_fee']:.4f})")
            else:
                print(f"  Polymarket NO Price: ${row['poly_no_price']:.4f} (Fee: $0.00 - no fees on Polymarket)")
                print(f"  Kalshi YES Price: ${row['kalshi_yes_price']:.4f} (Fee: ${row['kalshi_yes_fee']:.4f})")
            print("-" * 80)
        
        # Summary statistics
        print("\n" + "="*80)
        print("ARBITRAGE OPPORTUNITIES SUMMARY STATISTICS")
        print("="*80 + "\n")
        
        print(f"Total Opportunities Found: {len(opportunities_df)}")
        print(f"Average Profit: {opportunities_df['profit_pct'].mean():.2f}%")
        print(f"Median Profit: {opportunities_df['profit_pct'].median():.2f}%")
        print(f"Max Profit: {opportunities_df['profit_pct'].max():.2f}%")
        print(f"Min Profit: {opportunities_df['profit_pct'].min():.2f}%")
        
        print(f"\nStrategies:")
        print(opportunities_df['strategy'].value_counts())
        
        print(f"\nUnique Event Pairs with Opportunities: {opportunities_df[['kalshi_event_ticker', 'polymarket_event_id']].drop_duplicates().shape[0]}")
        print(f"Total Matched Pairs Checked: {len(arbitrage_possible)} event pairs with matched markets")
        
        # Show distribution of profits
        print(f"\nProfit Distribution:")
        print(opportunities_df['profit_pct'].describe())
    else:
        print("\n❌ No arbitrage opportunities found in any of the matched market pairs")


if __name__ == "__main__":
    main()

