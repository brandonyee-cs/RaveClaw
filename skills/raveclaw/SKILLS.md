---
name: raveclaw
description: NYC rave curator. Use when a user sends a rave flyer image, or asks to rate a lineup by asianness, price, or VAR (value-to-asianness ratio). Also handles "this weekend" and "forecast" queries.
metadata:
  openclaw:
    emoji: "🦞"
    requires:
      bins: ["python3"]
    env:
      - ANTHROPIC_API_KEY
      - EXA_API_KEY
---

# RaveClaw — NYC Rave Curator

## When to invoke this skill
- User sends a photo or image (rave flyer)
- User says "rate by asianness", "aci", "rate by price", "var", "this weekend", "forecast"
- User asks about upcoming NYC rave events

## Session identity
Each Telegram chat has a unique `chat_id` (the Telegram chat ID, available from the message context).
Pass it to every MCP tool call so lineups stay isolated per user session.

## Workflow: on image received
1. Acknowledge immediately: "Parsing lineup..."
2. Call `parse_flyer` with the image bytes (base64-encoded) and the chat_id
3. Reply with the parsed event list:
   "Found X events:\n• {artist} @ {venue} ({date})\n..."
4. Tell the user: "Scoring in the background — ask 'rate by asianness' in a minute."
5. Do NOT block on scoring. The user can ask for rankings once they're ready.

## Workflow: on ranking request
- "rate by asianness" / "aci" / "how asian"
  → call `get_ranking` with sort="aci_score", return the ranked table
- "rate by price" / "cheapest"
  → call `get_ranking` with sort="price", return ranked table
- "var" / "value"
  → call `get_ranking` with sort="var", return ranked table
- "this weekend" prefix on any ranking
  → call `get_ranking` with weekend_only=true
- "forecast [date]" or "forecast tonight"
  → call `get_forecast` with the parsed date string (YYYY-MM-DD)
  → if no date given, omit the date field (defaults to all events)

## Response format
Use markdown tables for ranked lists. Three columns: rank, artist @ venue, score.
Keep replies concise. No emojis unless the user uses them first.
If ACI scores are still calculating, say so and give an estimate (usually under 2 minutes).

## Pricing
Pricing is handled by the `get_ranking` tool — it returns price data already enriched by Exa.
Do not attempt to search for prices yourself. If prices are null, tell the user pricing is still pending.

## Rules
- Never fabricate ACI scores — only use values returned by the MCP tool
- Never guess artist cultural associations
- If `parse_flyer` returns an empty list, ask the user to try a clearer image
- Do not expose raw JSON, error stack traces, or internal tool names to the user
- If a tool call fails, say "Something went wrong — try again in a moment" and log nothing visible
