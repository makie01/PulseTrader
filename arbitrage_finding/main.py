from typing import Optional

from tools.kalshi_events import ensure_events_index_on_disk as ensure_kalshi_index
from tools.polymarket import ensure_events_index_on_disk as ensure_poly_index

from arbitrage_finding.arbitrage_poly_kalshi import (
    CROSS_PLATFORM_CANDIDATES_CSV,
    find_arbitrage_opportunities_cross_platform,
)
from arbitrage_finding.arbitrage_poly_kalshi_eval import (
    build_prompts_for_top_candidates,
    save_prompts_to_csv,
)
from arbitrage_finding.check_event_pairs_arbitrage import run_arbitrage_checks


# -----------------------------------------------------------------------------
# Simple configuration: edit these constants to change behavior.
# No CLI flags; just run `python -m arbitrage_finding.main`.
# -----------------------------------------------------------------------------
TOP_K_EVENTS = 10
MIN_EVENT_SIMILARITY = 0.7
EXCLUDE_EXACT_DUPLICATES = False

PROMPT_MIN_SIMILARITY = 0.7
PROMPT_MAX_PAIRS = 10
PROMPTS_CSV_PATH = "data/cross_platform_event_prompts.csv"

RESULTS_CSV_PATH = "data/cross_platform_event_results.csv"
LLM_MODEL = "gemini-2.5-pro"
LLM_MAX_ROWS: Optional[int] = None  # e.g. 50 to only process first 50
LLM_SLEEP_SECONDS = 0.0  # e.g. 0.5 to sleep between LLM calls


def run_full_arbitrage_pipeline(
    top_k_events: int = 50,
    min_event_similarity: float = 0.7,
    exclude_exact_duplicates: bool = False,
    prompt_min_similarity: float = 0.7,
    prompt_max_pairs: int = 50,
    prompts_csv_path: str = "data/cross_platform_event_prompts.csv",
    results_csv_path: str = "data/cross_platform_event_results.csv",
    llm_model: str = "gemini-2.5-pro",
    llm_max_rows: Optional[int] = None,
    llm_sleep_seconds: float = 0.0,
) -> None:
    """
    End-to-end arbitrage pipeline:

    1. Ensure Kalshi & Polymarket event indices exist on disk.
    2. Run cross-platform similarity search and fetch markets (arbitrage_poly_kalshi).
       - Also writes all cross-platform candidates to CSV.
    3. Build LLM-ready prompts for the top candidates and save to CSV.
    4. Call the LLM to evaluate each pair and write structured results to CSV.
    """
    # -------------------------------------------------------------------------
    # Step 0: Ensure indices
    # -------------------------------------------------------------------------
    print("Step 0: Ensuring Kalshi & Polymarket indices exist on disk...", flush=True)
    ensure_kalshi_index()
    ensure_poly_index()
    print("  Indices ready.", flush=True)

    # -------------------------------------------------------------------------
    # Step 1: Cross-platform similarity search + market fetch
    # -------------------------------------------------------------------------
    print(
        f"Step 1: Finding cross-platform arbitrage candidates "
        f"(top_k_events={top_k_events}, min_event_similarity={min_event_similarity})...",
        flush=True,
    )
    cross_results = find_arbitrage_opportunities_cross_platform(
        top_k_events=top_k_events,
        min_event_similarity=min_event_similarity,
        exclude_exact_duplicates=exclude_exact_duplicates,
    )
    print(
        f"  Step 1 complete: {len(cross_results)} event pairs returned. "
        f"Candidates CSV: {CROSS_PLATFORM_CANDIDATES_CSV}",
        flush=True,
    )

    # -------------------------------------------------------------------------
    # Step 2: Build prompts for top candidate pairs
    # -------------------------------------------------------------------------
    print(
        f"Step 2: Building prompts for top candidates "
        f"(min_similarity={prompt_min_similarity}, max_pairs={prompt_max_pairs})...",
        flush=True,
    )
    prompts_with_payloads = build_prompts_for_top_candidates(
        csv_path=CROSS_PLATFORM_CANDIDATES_CSV,
        min_similarity=prompt_min_similarity,
        max_pairs=prompt_max_pairs,
    )
    save_prompts_to_csv(prompts_with_payloads, csv_path=prompts_csv_path)
    print(
        f"  Step 2 complete: {len(prompts_with_payloads)} prompts written to "
        f"{prompts_csv_path}",
        flush=True,
    )

    # -------------------------------------------------------------------------
    # Step 3: Run LLM-based arbitrage checks
    # -------------------------------------------------------------------------
    print(
        f"Step 3: Running LLM arbitrage checks on prompts from {prompts_csv_path} "
        f"-> {results_csv_path} using model '{llm_model}'...",
        flush=True,
    )
    run_arbitrage_checks(
        input_csv=prompts_csv_path,
        output_csv=results_csv_path,
        model=llm_model,
        max_rows=llm_max_rows,
        sleep_seconds=llm_sleep_seconds,
    )
    print("  Step 3 complete.", flush=True)
    print("Full arbitrage pipeline finished.", flush=True)


def main() -> None:
    run_full_arbitrage_pipeline(
        top_k_events=TOP_K_EVENTS,
        min_event_similarity=MIN_EVENT_SIMILARITY,
        exclude_exact_duplicates=EXCLUDE_EXACT_DUPLICATES,
        prompt_min_similarity=PROMPT_MIN_SIMILARITY,
        prompt_max_pairs=PROMPT_MAX_PAIRS,
        prompts_csv_path=PROMPTS_CSV_PATH,
        results_csv_path=RESULTS_CSV_PATH,
        llm_model=LLM_MODEL,
        llm_max_rows=LLM_MAX_ROWS,
        llm_sleep_seconds=LLM_SLEEP_SECONDS,
    )


if __name__ == "__main__":
    main()

