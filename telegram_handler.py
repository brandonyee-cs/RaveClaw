import asyncio
import random
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from vision import parse_flyer
from aci import get_aci_score
from lineup import (
    save_lineup,
    update_aci,
    update_price,
    load_lineup
)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    await update.message.reply_text("Parsing lineup...")

    events = parse_flyer(bytes(image_bytes))

    if not events:
        await update.message.reply_text("Couldn't parse that image. Try again.")
        return

    save_lineup(chat_id, events)

    artist_list = "\n".join(
        f"• {e['artist']} @ {e['venue']} ({e['date']})" for e in events
    )
    await update.message.reply_text(
        f"Set list curated.\n\n{artist_list}\n\nFetching scores in the background..."
    )

    asyncio.create_task(enrich_lineup(chat_id, events))


async def enrich_lineup(chat_id: str, events: list):
    for event in events:
        artist = event["artist"]

        try:
            score = await asyncio.to_thread(get_aci_score, artist)
            if score is not None:
                update_aci(chat_id, artist, score)
                print(f"ACI {artist}: {score}")
        except Exception as e:
            print(f"ACI error {artist}: {e}")

        await asyncio.sleep(random.uniform(8, 15))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = update.message.text.lower().strip()

    lineup = load_lineup(chat_id)

    if not lineup:
        await update.message.reply_text(
            "No lineup loaded yet. Upload a photo from NYC_RAVES to get started."
        )
        return

    if "help" in text:
        await update.message.reply_text(
            "Commands:\n"
            "• Upload a photo → parse lineup\n"
            "• 'rate by asianness' → rank by ACI score\n"
            "• 'rate by price' → rank by ticket price\n"
            "• 'this weekend' → filter to upcoming Fri-Sun\n"
            "• 'var' → value-to-asianness ratio\n"
            "• 'forecast [date]' → ABG density forecast for a night"
        )
        return

    if "this weekend" in text:
        lineup = _filter_this_weekend(lineup)
        if not lineup:
            await update.message.reply_text("No events found this weekend.")
            return

    if any(x in text for x in ["asian", "asianness", "aci"]):
        await _reply_ranked(update, lineup, sort_key="aci_score", label="Asianness (ACI)")

    elif "price" in text:
        await _reply_ranked(update, lineup, sort_key="price", label="Price")

    elif "var" in text:
        await _reply_var(update, lineup)

    elif "forecast" in text:
        date_str = _extract_date(text)
        await _reply_forecast(update, lineup, date_str)

    else:
        await update.message.reply_text(
            "Try: 'rate by asianness', 'rate by price', 'this weekend', or 'var'"
        )


async def _reply_ranked(update: Update, lineup: list, sort_key: str, label: str):
    has_data = [e for e in lineup if e.get(sort_key) is not None]
    pending = [e for e in lineup if e.get(sort_key) is None]

    if not has_data:
        await update.message.reply_text(
            f"Still calculating {label} scores. Check back in a few minutes."
        )
        return

    reverse = sort_key == "aci_score"
    sorted_events = sorted(has_data, key=lambda x: x[sort_key], reverse=reverse)

    lines = [f"*Ranked by {label}*\n"]
    for i, e in enumerate(sorted_events, 1):
        val = e[sort_key]
        display = f"{val:.4f}%" if sort_key == "aci_score" else f"${val:.2f}"
        lines.append(f"{i}. {e['artist']} @ {e['venue']} — {display} ({e['date']})")

    if pending:
        lines.append(f"\n_{len(pending)} artists still calculating..._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _reply_var(update: Update, lineup: list):
    scored = [
        e for e in lineup
        if e.get("aci_score") is not None and e.get("price") is not None and e["price"] > 0
    ]

    if not scored:
        await update.message.reply_text("Need both ACI scores and prices to calculate VAR.")
        return

    for e in scored:
        e["var"] = round(e["aci_score"] / e["price"], 6)

    ranked = sorted(scored, key=lambda x: x["var"], reverse=True)

    lines = ["*Value-to-Asianness Ratio (ACI / Price)*\n"]
    for i, e in enumerate(ranked, 1):
        lines.append(
            f"{i}. {e['artist']} @ {e['venue']} — "
            f"VAR: {e['var']:.6f} "
            f"(ACI: {e['aci_score']:.4f}% / ${e['price']:.2f})"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _reply_forecast(update: Update, lineup: list, date_str: str | None):
    if date_str:
        events_on_date = [e for e in lineup if e["date"] == date_str]
    else:
        events_on_date = lineup

    scored = [e for e in events_on_date if e.get("aci_score") is not None]

    if not scored:
        await update.message.reply_text("No ACI scores available for that date yet.")
        return

    avg_aci = sum(e["aci_score"] for e in scored) / len(scored)
    max_event = max(scored, key=lambda x: x["aci_score"])

    label = date_str or "all dates"
    msg = (
        f"*ABG Night Forecast — {label}*\n\n"
        f"Average ACI across {len(scored)} events: *{avg_aci:.4f}%*\n"
        f"Highest ACI: {max_event['artist']} @ {max_event['venue']} ({max_event['aci_score']:.4f}%)"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


def _filter_this_weekend(lineup: list) -> list:
    today = datetime.today()
    days_until_friday = (4 - today.weekday()) % 7
    friday = today + timedelta(days=days_until_friday)
    sunday = friday + timedelta(days=2)

    friday_str = friday.strftime("%Y-%m-%d")
    sunday_str = sunday.strftime("%Y-%m-%d")

    return [e for e in lineup if friday_str <= e["date"] <= sunday_str]


def _extract_date(text: str) -> str | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group()
    return None