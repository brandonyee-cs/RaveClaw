"""
RaveClaw MCP Server

Exposes four tools to the OpenClaw agent:
  parse_flyer   — vision: image bytes → structured events
  score_lineup  — ACI scoring + Exa pricing (blocking, for CLI use)
  get_ranking   — return ranked lineup from current session state
  get_forecast  — ABG density forecast for a date or all events

Run as a stdio MCP server:
  python3 mcp_server.py

Registered in openclaw.json via:
  openclaw mcp add raveclaw --command "python3 /root/raveclaw/mcp_server.py"
"""

import asyncio
import base64
import json
import os
import sys
import re
import time
from datetime import datetime, timedelta
from typing import Any

# ── MCP SDK ───────────────────────────────────────────────────────────────────
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("mcp package not installed. Run: pip install mcp --break-system-packages", file=sys.stderr)
    sys.exit(1)

# ── RaveClaw modules ─────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from vision import parse_flyer as _parse_flyer
from aci import get_aci_score
from lineup import (
    save_lineup,
    update_aci,
    update_price,
    load_lineup,
)

# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="parse_flyer",
        description=(
            "Parse a rave flyer image into structured events. "
            "Returns a list of {artist, venue, date} objects. "
            "Call this when the user sends a photo."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "image_b64": {
                    "type": "string",
                    "description": "Base64-encoded image bytes (JPEG or PNG).",
                },
                "chat_id": {
                    "type": "string",
                    "description": "Telegram chat ID — used to namespace the stored lineup.",
                },
            },
            "required": ["image_b64", "chat_id"],
        },
    ),
    Tool(
        name="score_lineup",
        description=(
            "Run ACI scoring and Exa ticket pricing on the stored lineup for a session. "
            "Blocking — use for CLI or batch runs. "
            "In the Telegram flow, ACI is enriched async; call get_ranking instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "skip_aci": {"type": "boolean", "default": False},
                "skip_pricing": {"type": "boolean", "default": False},
            },
            "required": ["chat_id"],
        },
    ),
    Tool(
        name="get_ranking",
        description=(
            "Return the ranked lineup for a session. "
            "sort can be 'aci_score' (default), 'price', or 'var' (ACI/price ratio). "
            "Set weekend_only=true to filter to the coming Friday–Sunday."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "sort": {
                    "type": "string",
                    "enum": ["aci_score", "price", "var"],
                    "default": "aci_score",
                },
                "weekend_only": {"type": "boolean", "default": False},
            },
            "required": ["chat_id"],
        },
    ),
    Tool(
        name="get_forecast",
        description=(
            "Return an ABG density forecast: average ACI score, top artist, "
            "and event count. Optionally filter to a specific date (YYYY-MM-DD)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "date": {
                    "type": "string",
                    "description": "ISO date string YYYY-MM-DD, or omit for all events.",
                },
            },
            "required": ["chat_id"],
        },
    ),
]

# ── Tool implementations ──────────────────────────────────────────────────────

def _tool_parse_flyer(args: dict) -> dict:
    image_bytes = base64.b64decode(args["image_b64"])
    chat_id = args["chat_id"]
    events = _parse_flyer(image_bytes)
    if events:
        save_lineup(chat_id, events)
    return {"events": events, "count": len(events)}


def _tool_score_lineup(args: dict) -> dict:
    chat_id = args["chat_id"]
    skip_aci = args.get("skip_aci", False)
    skip_pricing = args.get("skip_pricing", False)

    events = load_lineup(chat_id)
    if not events:
        return {"error": "No lineup found for this session. Parse a flyer first."}

    if not skip_aci:
        for i, event in enumerate(events):
            score = get_aci_score(event["artist"])
            if score is not None:
                update_aci(chat_id, event["artist"], score)
            if i < len(events) - 1:
                time.sleep(1)

    if not skip_pricing:
        _enrich_prices(events, chat_id)

    return _build_output(load_lineup(chat_id))


def _tool_get_ranking(args: dict) -> dict:
    chat_id = args["chat_id"]
    sort_key = args.get("sort", "aci_score")
    weekend_only = args.get("weekend_only", False)

    lineup = load_lineup(chat_id)
    if not lineup:
        return {"error": "No lineup found for this session. Parse a flyer first."}

    if weekend_only:
        lineup = _filter_weekend(lineup)
        if not lineup:
            return {"error": "No events found this weekend."}

    return _build_output(lineup, sort_key=sort_key)


def _tool_get_forecast(args: dict) -> dict:
    chat_id = args["chat_id"]
    date_str = args.get("date")

    lineup = load_lineup(chat_id)
    if not lineup:
        return {"error": "No lineup found for this session."}

    events = [e for e in lineup if e["date"] == date_str] if date_str else lineup
    scored = [e for e in events if e.get("aci_score") is not None]

    if not scored:
        return {"error": "No ACI scores available yet. Try again in a moment."}

    avg_aci = round(sum(e["aci_score"] for e in scored) / len(scored), 4)
    top = max(scored, key=lambda x: x["aci_score"])

    return {
        "date": date_str or "all",
        "avg_aci": avg_aci,
        "event_count": len(scored),
        "top_artist": top["artist"],
        "top_venue": top["venue"],
        "top_aci": top["aci_score"],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _extract_price(results) -> float | None:
    if not results.results:
        return None
    for result in results.results:
        text = getattr(result, "text", "") or ""
        url = getattr(result, "url", "") or ""
        if any(x in url for x in ["stubhub", "vividseats", "seatgeek"]):
            continue
        matches = re.findall(r"\$(\d+(?:\.\d{2})?)", text)
        if matches:
            prices = [float(m) for m in matches if 5 <= float(m) <= 500]
            if prices:
                return min(prices)
    return None


def _filter_weekend(lineup: list) -> list:
    today = datetime.today()
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    sunday = friday + timedelta(days=2)
    return [
        e for e in lineup
        if friday.strftime("%Y-%m-%d") <= e.get("date", "") <= sunday.strftime("%Y-%m-%d")
    ]


def _build_output(lineup: list, sort_key: str = "aci_score") -> dict:
    scored_aci = [e for e in lineup if e.get("aci_score") is not None]
    scored_price = [e for e in lineup if e.get("price") is not None]
    scored_both = [
        e for e in lineup
        if e.get("aci_score") is not None
        and e.get("price") is not None
        and e["price"] > 0
    ]
    for e in scored_both:
        e["var"] = round(e["aci_score"] / e["price"], 6)

    missing = [
        e for e in lineup
        if e.get("aci_score") is None or e.get("price") is None
    ]

    ranked: list = []
    if sort_key == "aci_score":
        ranked = sorted(scored_aci, key=lambda x: x["aci_score"], reverse=True)
    elif sort_key == "price":
        ranked = sorted(scored_price, key=lambda x: x["price"])
    elif sort_key == "var":
        ranked = sorted(scored_both, key=lambda x: x["var"], reverse=True)

    return {
        "sort": sort_key,
        "ranked": ranked,
        "total": len(lineup),
        "missing_data": len(missing),
        "pending": [e["artist"] for e in missing],
    }


# ── MCP server entrypoint ─────────────────────────────────────────────────────

app = Server("raveclaw")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "parse_flyer":
            result = await asyncio.to_thread(_tool_parse_flyer, arguments)
        elif name == "score_lineup":
            result = await asyncio.to_thread(_tool_score_lineup, arguments)
        elif name == "get_ranking":
            result = await asyncio.to_thread(_tool_get_ranking, arguments)
        elif name == "get_forecast":
            result = await asyncio.to_thread(_tool_get_forecast, arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with stdio_server() as streams:
        await app.run(*streams, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
