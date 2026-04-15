import os
import sys
import re
import time
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ─── Args ─────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="RaveClaw pipeline runner")
parser.add_argument("images", nargs="*", help="Image files to process")
parser.add_argument("--skip-aci",       action="store_true")
parser.add_argument("--skip-pricing",   action="store_true")
parser.add_argument("--analysis-only",  action="store_true")
parser.add_argument("--chat-id",        default="pipeline")
args = parser.parse_args()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def header(msg):   print(f"\n{'═'*55}\n  {msg}\n{'═'*55}")
def step(msg):     print(f"\n  → {msg}")
def ok(msg):       print(f"    \033[92m✓\033[0m {msg}")
def warn(msg):     print(f"    \033[93m⚠\033[0m {msg}")
def info(msg):     print(f"    {msg}")


# ─── Phase 1: Vision ──────────────────────────────────────────────────────────

def run_vision(image_paths: list, chat_id: str) -> list:
    header("PHASE 1: Parsing Images")

    from vision import parse_flyer
    from lineup import save_lineup

    all_events = []

    for path in image_paths:
        step(f"Parsing {os.path.basename(path)}")
        try:
            with open(path, "rb") as f:
                events = parse_flyer(f.read())
            ok(f"Found {len(events)} events")
            for e in events:
                info(f"  {e['date']}  {e['artist']:<25} @ {e['venue']}")
            all_events.extend(events)
        except Exception as e:
            warn(f"Failed to parse {path}: {e}")

    if not all_events:
        print("\n  No events parsed. Exiting.")
        sys.exit(1)

    # Deduplicate by artist + date
    seen, deduped = set(), []
    for e in all_events:
        key = (e["artist"].lower(), e["date"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    if len(deduped) < len(all_events):
        ok(f"Deduplicated {len(all_events)} → {len(deduped)} events")

    save_lineup(chat_id, deduped)
    ok(f"Saved {len(deduped)} events to lineup.json")

    return deduped


# ─── Phase 2: ACI ─────────────────────────────────────────────────────────────

def run_aci(events: list, chat_id: str):
    header("PHASE 2: ACI Scoring (Exa)")

    from aci import get_aci_score
    from lineup import update_aci

    total = len(events)
    for i, event in enumerate(events, 1):
        artist = event["artist"]
        step(f"[{i}/{total}] {artist}")

        try:
            score = get_aci_score(artist)
            if score is not None:
                update_aci(chat_id, artist, score)
                ok(f"ACI: {score:.4f}%")
            else:
                warn("No data returned")
        except Exception as e:
            warn(f"Failed: {e}")

        if i < total:
            time.sleep(1)  # light rate limit between Exa calls

    ok("ACI scoring complete")


# ─── Phase 3: Pricing ─────────────────────────────────────────────────────────

def run_pricing(events: list, chat_id: str):
    header("PHASE 3: Ticket Pricing (Exa)")

    from exa_py import Exa
    from lineup import update_price

    exa = Exa(api_key=os.getenv("EXA_API_KEY"))
    total = len(events)

    for i, event in enumerate(events, 1):
        artist = event["artist"]
        venue  = event["venue"]
        date   = event["date"]

        step(f"[{i}/{total}] {artist} @ {venue}")

        try:
            results = exa.search(
                f"{artist} {venue} NYC {date} tickets",
                include_domains=["dice.fm", "ra.co"],
                num_results=3
            )
            price = _extract_price(results)

            if price is not None:
                update_price(chat_id, artist, price)
                ok(f"${price:.2f}")
            else:
                warn("No price found on dice.fm or ra.co")

        except Exception as e:
            warn(f"Exa query failed: {e}")

        time.sleep(1)

    ok("Pricing complete")


def _extract_price(results) -> float | None:
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


# ─── Phase 4: Analysis ────────────────────────────────────────────────────────

def run_analysis(chat_id: str):
    header("PHASE 4: Analysis")

    from lineup import load_lineup

    events = load_lineup(chat_id)
    if not events:
        warn("No events in lineup.json. Run without --analysis-only first.")
        return

    scored_aci   = [e for e in events if e.get("aci_score") is not None]
    scored_price = [e for e in events if e.get("price") is not None]
    scored_both  = [e for e in events if e.get("aci_score") is not None and e.get("price") is not None]

    info(f"\n  Total events:    {len(events)}")
    info(f"  ACI scored:      {len(scored_aci)}/{len(events)}")
    info(f"  Prices found:    {len(scored_price)}/{len(events)}")
    info(f"  Fully enriched:  {len(scored_both)}/{len(events)}")

    if scored_aci:
        header("RANKED BY ASIANNESS (ACI)")
        _print_table(
            sorted(scored_aci, key=lambda x: x["aci_score"], reverse=True),
            "aci_score", lambda v: f"{v:.4f}%"
        )

    if scored_price:
        header("RANKED BY PRICE (cheapest first)")
        _print_table(
            sorted(scored_price, key=lambda x: x["price"]),
            "price", lambda v: f"${v:.2f}"
        )

    if scored_both:
        header("VALUE-TO-ASIANNESS RATIO (ACI / Price)")
        for e in scored_both:
            e["var"] = round(e["aci_score"] / e["price"], 6)
        _print_table(
            sorted(scored_both, key=lambda x: x["var"], reverse=True),
            "var", lambda v: f"{v:.6f}"
        )
        info("\n  Higher VAR = more ABG density per dollar spent")

    # This weekend filter
    today  = datetime.today()
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    sunday = friday + timedelta(days=2)
    weekend = [e for e in events if friday.strftime("%Y-%m-%d") <= e.get("date", "") <= sunday.strftime("%Y-%m-%d")]

    if weekend:
        header(f"THIS WEEKEND ({friday.strftime('%Y-%m-%d')} – {sunday.strftime('%Y-%m-%d')})")
        for e in weekend:
            aci   = f"{e['aci_score']:.4f}%" if e.get("aci_score") else "pending"
            price = f"${e['price']:.2f}"     if e.get("price")     else "pending"
            info(f"  {e['date']}  {e['artist']:<25} @ {e['venue']:<25}  ACI: {aci:<12}  Price: {price}")

    missing = [e for e in events if e.get("aci_score") is None or e.get("price") is None]
    if missing:
        header("MISSING DATA")
        for e in missing:
            gaps = []
            if e.get("aci_score") is None: gaps.append("ACI")
            if e.get("price")     is None: gaps.append("price")
            info(f"  {e['artist']:<25} missing: {', '.join(gaps)}")


def _print_table(events, sort_key, fmt):
    w = 25
    info(f"\n  {'#':<4} {'Artist':<{w}} {'Venue':<{w}} {'Date':<12} Score")
    info(f"  {'─'*4} {'─'*w} {'─'*w} {'─'*12} {'─'*12}")
    for i, e in enumerate(events, 1):
        info(f"  {i:<4} {e['artist']:<{w}} {e['venue']:<{w}} {e['date']:<12} {fmt(e[sort_key])}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    chat_id = args.chat_id

    print("\n🦅 RaveClaw Pipeline")
    print(f"   ACI:     {'OFF' if args.skip_aci     else 'ON'}")
    print(f"   Pricing: {'OFF' if args.skip_pricing else 'ON'}")

    if args.analysis_only:
        run_analysis(chat_id)
        return

    image_paths = args.images or sorted(
        f for f in os.listdir(".") if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )

    if not image_paths:
        print("\n  No images found.")
        sys.exit(1)

    info(f"\n  Found {len(image_paths)} image(s): {', '.join(image_paths)}")

    events = run_vision(image_paths, chat_id)

    if not args.skip_aci:     run_aci(events, chat_id)
    if not args.skip_pricing: run_pricing(events, chat_id)

    run_analysis(chat_id)

    print(f"\n{'═'*55}")
    print("  Done. Results saved to lineup.json.")
    print(f"{'═'*55}\n")


if __name__ == "__main__":
    main()