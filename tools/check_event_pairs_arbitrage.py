import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import dotenv
import pandas as pd
from google import genai

# Load environment variables (same pattern as tools/emb.py)
dotenv.load_dotenv()


_LLM_CLIENT: Optional[genai.Client] = None


def _get_llm_client() -> genai.Client:
    """Lazily construct a reusable genai.Client for text generation.

    Uses the same Vertex AI-related env vars as the embedding client:
    - GOOGLE_GENAI_USE_VERTEXAI
    - GOOGLE_GENAI_PROJECT
    - GOOGLE_GENAI_LOCATION
    """
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        _LLM_CLIENT = genai.Client(
            vertexai=os.getenv("GOOGLE_GENAI_USE_VERTEXAI"),
            project=os.getenv("GOOGLE_GENAI_PROJECT"),
            location=os.getenv("GOOGLE_GENAI_LOCATION"),
        )
    return _LLM_CLIENT


def _call_llm(prompt: str, model: str = "gemini-2.5-pro") -> str:
    """Send a prompt to the LLM and return the raw text response.

    We keep this very simple: one prompt -> one text answer.
    """
    client = _get_llm_client()
    resp = client.models.generate_content(model=model, contents=prompt)

    # Prefer the convenience .text attr if available (newer genai library)
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    # Fallback: reconstruct from candidates/parts
    if hasattr(resp, "candidates") and resp.candidates:
        parts: List[str] = []
        for cand in resp.candidates:
            if not getattr(cand, "content", None):
                continue
            for part in getattr(cand.content, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str):
                    parts.append(part_text)
        if parts:
            return "\n".join(parts)

    # Last resort: string representation
    return str(resp)


def _safe_parse_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON parse of the LLM output.

    Returns a dict with:
    - could_have_arbitrage
    - reasons
    - matched_market_pairs
    - parse_error (empty string if no error)
    """
    base: Dict[str, Any] = {
        "could_have_arbitrage": None,
        "reasons": "",
        "matched_market_pairs": None,
        "parse_error": "",
    }

    if not text or not text.strip():
        base["parse_error"] = "empty_response"
        return base

    # Try to locate a JSON object if the model included extra commentary.
    candidate = text.strip()
    first_brace = candidate.find("{")
    last_brace = candidate.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = candidate[first_brace : last_brace + 1]

    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            base["could_have_arbitrage"] = obj.get("could_have_arbitrage")
            base["reasons"] = obj.get("reasons", "")
            base["matched_market_pairs"] = obj.get("matched_market_pairs")
            return base
        base["parse_error"] = "not_a_dict"
        return base
    except json.JSONDecodeError as e:
        base["parse_error"] = f"json_error: {e}"
        return base


def run_arbitrage_checks(
    input_csv: str = "data/cross_platform_event_prompts.csv",
    output_csv: str = "data/cross_platform_event_results.csv",
    model: str = "gemini-2.5-pro",
    max_rows: Optional[int] = None,
    sleep_seconds: float = 0.0,
) -> None:
    """Loop over all event pairs/prompts and query the LLM.

    Reads prompts from `input_csv` (produced by arbitrage_poly_kalshi_eval.py),
    sends each prompt to the LLM, and writes results to `output_csv` with
    both metadata and parsed JSON fields.
    """
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)

    # Load prompts into a DataFrame for easier inspection / slicing.
    df = pd.read_csv(input_csv)
    if max_rows is not None:
        df = df.head(max_rows)
    total_rows = len(df)

    print(
        f"Running arbitrage checks on {total_rows} event pairs "
        f"from {input_csv} -> {output_csv} using model {model}",
        flush=True,
    )

    fieldnames = [
        # Metadata from the prompts CSV
        "kalshi_ticker",
        "polymarket_id",
        "similarity",
        "kalshi_title",
        "polymarket_title",
        "kalshi_markets_count",
        "polymarket_markets_count",
        # Prompt and raw model output
        "prompt",
        "llm_raw_response",
        # Parsed fields (if JSON parse succeeds)
        "could_have_arbitrage",
        "reasons",
        "matched_market_pairs_json",
        "parse_error",
    ]

    with open(output_csv, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        records = df.to_dict(orient="records")

        for idx, row in enumerate(records, start=1):
            if idx == 1 or idx % 5 == 0 or idx == total_rows:
                print(
                    f"[{idx}/{total_rows}] Processing pair "
                    f"{row.get('kalshi_ticker')} vs {row.get('polymarket_id')}",
                    flush=True,
                )

            prompt = row.get("prompt", "")
            if not prompt:
                continue

            try:
                raw_resp = _call_llm(prompt, model=model)
                # Show the raw response so you can see progress and content.
                print(
                    f"[{idx}/{total_rows}] LLM response:\n{raw_resp}\n",
                    flush=True,
                )
            except Exception as e:  # pragma: no cover - defensive
                raw_resp = ""
                parsed = {
                    "could_have_arbitrage": None,
                    "reasons": "",
                    "matched_market_pairs": None,
                    "parse_error": f"llm_error: {e}",
                }
            else:
                parsed = _safe_parse_json(raw_resp)

            matched_pairs = parsed.get("matched_market_pairs")
            matched_pairs_json = (
                json.dumps(matched_pairs) if matched_pairs is not None else ""
            )

            writer.writerow(
                {
                    "kalshi_ticker": row.get("kalshi_ticker"),
                    "polymarket_id": row.get("polymarket_id"),
                    "similarity": row.get("similarity"),
                    "kalshi_title": row.get("kalshi_title"),
                    "polymarket_title": row.get("polymarket_title"),
                    "kalshi_markets_count": row.get("kalshi_markets_count"),
                    "polymarket_markets_count": row.get("polymarket_markets_count"),
                    "prompt": prompt,
                    "llm_raw_response": raw_resp,
                    "could_have_arbitrage": parsed.get("could_have_arbitrage"),
                    "reasons": parsed.get("reasons"),
                    "matched_market_pairs_json": matched_pairs_json,
                    "parse_error": parsed.get("parse_error"),
                }
            )

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)


if __name__ == "__main__":
    # Simple CLI entry point: process all rows in the prompts CSV
    # and write results to data/cross_platform_event_results.csv
    run_arbitrage_checks()
