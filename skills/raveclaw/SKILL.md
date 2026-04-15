---
name: raveclaw
description: NYC rave curator. Use when a user sends a rave flyer image, or asks to rate a lineup by asianness, price, VAR, this weekend, forecast, or help.
metadata: {"openclaw": {"emoji": "🦞", "requires": {"bins": ["python3"]}}}
---

# RaveClaw

The Python backend is ALREADY INSTALLED at /sandbox/RaveClaw.
You have exec access. Use it.
Do not offer to build, create, or write any code.
Do not reference MCP servers.

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
2. Save the image to /tmp/flyer.jpg
3. Run with exec: cd /sandbox/RaveClaw && python3 skill.py /tmp/flyer.jpg --skip-aci --skip-pricing --chat-id telegram
4. Parse the JSON output. The events array contains artist, venue, date objects.
5. Reply: Found X events, then list each as Artist @ Venue (date)
6. Reply: Scoring in background. Ask rate by asianness in about a minute.
7. Then run with exec in background: cd /sandbox/RaveClaw && python3 skill.py /tmp/flyer.jpg --skip-pricing --chat-id telegram

## rate by asianness / aci
Run with exec: cd /sandbox/RaveClaw && python3 -c "from lineup import load_lineup; import json; data=load_lineup('telegram'); scored=[e for e in data if e.get('aci_score') is not None]; print('PENDING') if not scored else print(json.dumps(sorted(scored,key=lambda x:x['aci_score'],reverse=True)))"
If output is PENDING reply: Still scoring, check back in a minute.
Otherwise format as markdown table: rank, artist at venue, date, ACI score.

## rate by price
Run with exec: cd /sandbox/RaveClaw && python3 -c "from lineup import load_lineup; import json; data=load_lineup('telegram'); scored=[e for e in data if e.get('price') is not None]; print('PENDING') if not scored else print(json.dumps(sorted(scored,key=lambda x:x['price'])))"
Format as table: rank, artist at venue, date, price.

## var
Run with exec: cd /sandbox/RaveClaw && python3 -c "from lineup import load_lineup; import json; data=load_lineup('telegram'); both=[e for e in data if e.get('aci_score') and e.get('price')]; [e.update({'var':round(e['aci_score']/e['price'],4)}) for e in both]; print('PENDING') if not both else print(json.dumps(sorted(both,key=lambda x:x['var'],reverse=True)))"
Format as table: rank, artist at venue, VAR, ACI, price.

## this weekend
Run the rate by asianness command but add a date filter for the coming Friday through Sunday before sorting.

## forecast
Run with exec: cd /sandbox/RaveClaw && python3 -c "from lineup import load_lineup; data=load_lineup('telegram'); scored=[e for e in data if e.get('aci_score') is not None]; top=max(scored,key=lambda x:x['aci_score']) if scored else None; avg=round(sum(e['aci_score'] for e in scored)/len(scored),2) if scored else 0; print(f'scored={len(scored)} avg={avg} top_artist={top[\"artist\"] if top else None} top_aci={top[\"aci_score\"] if top else 0}')"
Reply with a summary: average ACI, top artist, number of events scored.

## rules
- Always use chat_id telegram
- ANTHROPIC_API_KEY is in your environment
- Never show raw JSON or Python tracebacks to the user
- If exec fails, reply: Something went wrong, try again
- No emojis unless the user uses them first
