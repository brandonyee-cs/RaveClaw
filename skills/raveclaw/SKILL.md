---
name: raveclaw
description: NYC rave curator. Use when a user sends a rave flyer image, or asks to rate a lineup by asianness, price, VAR, this weekend, forecast, or help.
metadata: {"openclaw": {"emoji": "🦞", "mcp": "raveclaw", "requires": {"bins": ["python3"]}}}
---

# RaveClaw

All operations go through the **raveclaw MCP server**.
Do not use exec. Do not run Python scripts directly. Do not reference file paths.

## help
Reply with exactly this:
Commands:
- Send a flyer photo to parse lineup
- rate by asianness - rank by ACI score
- rate by price - rank by ticket price
- var - value-to-asianness ratio
- this weekend - filter to Fri-Sun
- forecast - ABG density forecast

## on image received
1. Reply: Parsing lineup...
2. Base64-encode the image bytes.
3. Call MCP tool `parse_flyer` with:
   - `image_b64`: the base64 string
   - `chat_id`: "telegram"
4. The response contains an `events` array with artist, venue, date objects.
5. Reply: Found X events, then list each as Artist @ Venue (date)
6. Reply: Scoring in background. Try "rate by asianness" in about a minute.
7. Call MCP tool `score_lineup` with:
   - `chat_id`: "telegram"
   - `skip_pricing`: true
   (This call is slow — fire it and let it run; don't block the user on it.)

## rate by asianness / aci
Call MCP tool `get_ranking` with:
  - `chat_id`: "telegram"
  - `sort`: "aci_score"

If `ranked` is empty and `pending` is non-empty, reply: Still scoring, check back in a minute.
Otherwise format as a markdown table: rank, Artist @ Venue, date, ACI score.

## rate by price
Call MCP tool `get_ranking` with:
  - `chat_id`: "telegram"
  - `sort`: "price"

Format as a markdown table: rank, Artist @ Venue, date, price.

## var
Call MCP tool `get_ranking` with:
  - `chat_id`: "telegram"
  - `sort`: "var"

Format as a markdown table: rank, Artist @ Venue, VAR, ACI, price.

## this weekend
Call MCP tool `get_ranking` with:
  - `chat_id`: "telegram"
  - `sort`: "aci_score"
  - `weekend_only`: true

Format as a markdown table: rank, Artist @ Venue, date, ACI score.
If the response returns an error about no weekend events, relay it plainly.

## forecast
Call MCP tool `get_forecast` with:
  - `chat_id`: "telegram"
  - (omit `date` to forecast across all events)

Reply with a summary: average ACI, top artist, number of events scored.

## rules
- Always use chat_id "telegram"
- Never show raw JSON or tracebacks to the user
- If a tool returns an `error` key, relay the message plainly and suggest next steps
- No emojis unless the user uses them first
