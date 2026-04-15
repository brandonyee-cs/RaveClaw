import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EXA_API_KEY        = os.getenv("EXA_API_KEY")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")

PRICE_DOMAINS         = ["dice.fm", "ra.co"]
PRICE_EXCLUDE_DOMAINS = ["stubhub.com", "vividseats.com", "seatgeek.com"]

LINEUP_FILE      = "lineup.json"
ACI_HISTORY_FILE = "aci_history.json"