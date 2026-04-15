import anthropic
import base64
import json
import re
from settings import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

VISION_PROMPT = """
You are parsing an NYC Raves event schedule image.
Extract every row from the table and return ONLY a JSON array with no extra text.

Each object must have exactly these keys:
- "artist": string (the DJ or event name)
- "venue": string (the location)
- "date": string (in YYYY-MM-DD format, assume year 2026)

Rules:
- If an artist cell contains two names (e.g. "Juliet Fox & Joyhauser"), keep them together as one string
- Do not include the header row
- Do not add any commentary, markdown, or backticks — raw JSON array only

Example output:
[
  {"artist": "ISOxo", "venue": "Brooklyn Storehouse", "date": "2026-05-01"},
  {"artist": "PEEKABOO", "venue": "Brooklyn Steel", "date": "2026-05-02"}
]
"""


def parse_flyer(image_bytes: bytes) -> list[dict]:
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": VISION_PROMPT
                    }
                ],
            }
        ],
    )

    raw = message.content[0].text.strip()

    raw = re.sub(r"```json|```", "", raw).strip()

    events = json.loads(raw)

    cleaned = []
    for e in events:
        if all(k in e for k in ("artist", "venue", "date")):
            cleaned.append({
                "artist": e["artist"].strip(),
                "venue": e["venue"].strip(),
                "date": e["date"].strip()
            })

    return cleaned