"""
RaveClaw — OpenClaw Skill Entry Point

Exposes a single callable interface: process_flyer()
Agents invoke this with an image path or bytes and get back a ranked lineup.
"""

import os
import re
import time
import json
from typing import Optional

from vision import parse_flyer
from aci import get_aci_score
from lineup import save_lineup, update_aci, update_price, load_lineup


# ──────────────────────────────────────────────────────────────────────────────
# Public skill interface
# ──────────────────────────────────────────────────────────────────────────────

def process_flyer(
    image: bytes,
    chat_id: str = "default",
    skip_aci: bool = False,
    skip_pricing: bool = False,
) -> dict:
    """
    Core RaveClaw skill. Takes a rave flyer image and returns a ranked lineup.

    Input:
        image       - raw image bytes (JPEG or PNG)
        chat_id     - session key for lineup persistence
        skip_aci    - skip ACI scoring (faster, less insight)
        skip_pricing - skip Exa ticket price lookups

    Output:
        {
            "events": [...],           # raw extracted events
            "ranked_aci": [...],       # sorted by ACI score desc
            "ranked_price": [...],     # sorted by price asc
            "ranked_var": [...],       # sorted by VAR (ACI/price) desc
            "missing": [...]           # events with incomplete data
        }
    """
    # Phase 1: vision
    events = parse_flyer(image)
    if not events:
        return {"error": "No events parsed from image."}

    # Deduplicate
    seen, deduped = set(), []
    for e in events:
        key = (e["artist"].lower(), e["date"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    events = deduped

    save_lineup(chat_id, events)

    # Phase 2: ACI scoring
    if not skip_aci:
        for i, event in enumerate(events):
            score = get_aci_score(event["artist"])
            if score is not None:
                update_aci(chat_id, event["artist"], score)
            if i < len(events) - 1:
                time.sleep(1)

    # Phase 3: ticket pricing
    if not skip_pricing:
        _enrich_prices(events, chat_id)

    # Phase 4: build output
    lineup = load_lineup(chat_id)
    return _build_output(lineup)


def get_ranking(chat_id: str = "default") -> dict:
    """
    Re-run the analysis on an already-enriched lineup.
    Useful for Telegram bots that enrich asynchronously.
    """
    lineup = load_lineup(chat_id)
    if not lineup:
        return {"error": "No lineup found for this session."}
    return _build_output(lineup)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _enrich_prices(events: list, chat_id: str):
    try:
        from exa_py import Exa
        exa = Exa(api_key=os.getenv("EXA_API_KEY"))
    except Exception:
        return

    for i, event in enumerate(events):
        try:
            results = exa.search(
                f"{event['artist']} {event['venue']} NYC {event['date']} tickets",
                include_domains=["dice.fm", "ra.co"],
                num_results=3,
            )
            price = _extract_price(results)
            if price is not None:
                update_price(chat_id, event["artist"], price)
        except Exception:
            pass
        if i < len(events) - 1:
            time.sleep(1)


def _extract_price(results) -> Optional[float]:
    if not results.results:
        return None
    for result in results.results:
        text = getattr(result, "text", "") or ""
        url  = getattr(result, "url",  "") or ""
        if any(x in url for x in ["stubhub", "vividseats", "seatgeek"]):
            continue
        matches = re.findall(r"\$(\d+(?:\.\d{2})?)", text)
        if matches:
            prices = [float(m) for m in matches if 5 <= float(m) <= 500]
            if prices:
                return min(prices)
    return None


def _build_output(lineup: list) -> dict:
    scored_aci   = [e for e in lineup if e.get("aci_score") is not None]
    scored_price = [e for e in lineup if e.get("price") is not None]
    scored_both  = [
        e for e in lineup
        if e.get("aci_score") is not None and e.get("price") is not None and e["price"] > 0
    ]

    for e in scored_both:
        e["var"] = round(e["aci_score"] / e["price"], 6)

    return {
        "events":       lineup,
        "ranked_aci":   sorted(scored_aci,   key=lambda x: x["aci_score"], reverse=True),
        "ranked_price": sorted(scored_price, key=lambda x: x["price"]),
        "ranked_var":   sorted(scored_both,  key=lambda x: x["var"], reverse=True),
        "missing":      [e for e in lineup if e.get("aci_score") is None or e.get("price") is None],
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI shim (for local testing and the demo)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="RaveClaw skill — local test runner")
    parser.add_argument("image", help="Path to a flyer image")
    parser.add_argument("--skip-aci",     action="store_true")
    parser.add_argument("--skip-pricing", action="store_true")
    parser.add_argument("--chat-id",      default="cli")
    args = parser.parse_args()

    with open(args.image, "rb") as f:
        image_bytes = f.read()

    result = process_flyer(
        image_bytes,
        chat_id=args.chat_id,
        skip_aci=args.skip_aci,
        skip_pricing=args.skip_pricing,
    )

    print(json.dumps(result, indent=2))