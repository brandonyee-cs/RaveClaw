import json
import os
from datetime import datetime
from settings import LINEUP_FILE, ACI_HISTORY_FILE


def save_lineup(chat_id: str, events: list):
    data = load_all()
    data[str(chat_id)] = [
        {
            "artist": e["artist"],
            "venue": e["venue"],
            "date": e["date"],
            "aci_score": None,
            "price": None
        }
        for e in events
    ]
    _write(LINEUP_FILE, data)


def update_aci(chat_id: str, artist: str, score: float):
    data = load_all()
    for event in data.get(str(chat_id), []):
        if event["artist"].lower() == artist.lower():
            event["aci_score"] = score
    _write(LINEUP_FILE, data)
    _log_aci_history(artist, score)


def update_price(chat_id: str, artist: str, price: float):
    data = load_all()
    for event in data.get(str(chat_id), []):
        if event["artist"].lower() == artist.lower():
            event["price"] = price
    _write(LINEUP_FILE, data)


def load_lineup(chat_id: str) -> list:
    return load_all().get(str(chat_id), [])


def load_all() -> dict:
    if not os.path.exists(LINEUP_FILE):
        return {}
    with open(LINEUP_FILE, "r") as f:
        return json.load(f)


def clear_lineup(chat_id: str):
    data = load_all()
    data.pop(str(chat_id), None)
    _write(LINEUP_FILE, data)


def _log_aci_history(artist: str, score: float):
    if not os.path.exists(ACI_HISTORY_FILE):
        history = {}
    else:
        with open(ACI_HISTORY_FILE, "r") as f:
            history = json.load(f)

    if artist not in history:
        history[artist] = []

    history[artist].append({
        "score": score,
        "timestamp": datetime.utcnow().isoformat()
    })

    _write(ACI_HISTORY_FILE, history)


def load_aci_history(artist: str) -> list:
    if not os.path.exists(ACI_HISTORY_FILE):
        return []
    with open(ACI_HISTORY_FILE, "r") as f:
        history = json.load(f)
    return history.get(artist, [])


def _write(path: str, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)