import anthropic
from settings import ANTHROPIC_API_KEY

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


PROMPT = """Score how associated "{artist}" is with the ABG/Asian-American rave subculture on a scale of 0 to 100.

Context:
- ABG = Asian Baby Girl / Asian Baby Boy subculture
- Artists like ISOxo, Knock2, KSHMR, AHEE score high (60-100)
- Mainstream crossover artists like Seven Lions score medium (20-40)
- European techno/deep house artists with no Asian-American following score low (0-10)
- Base your score on the artist's actual fanbase demographics and cultural associations

Return ONLY a single number between 0 and 100. No explanation, no text, just the number."""


def get_aci_score(artist_name: str) -> float | None:
    client = _get_client()

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": PROMPT.format(artist=artist_name)
            }]
        )
        raw = response.content[0].text.strip()
        return round(float(raw), 4)

    except Exception as e:
        print(f"    LLM ACI failed for {artist_name}: {e}")
        return None