"""Live diagnostics: connects to the /live WebSocket and summarizes traffic.

Usage:  python scripts/live_check.py [seconds]
Auth uses the API_KEY from backend/.env (legacy admin-equivalent key).
"""
import asyncio
import collections
import json
import sys
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402


async def main(seconds: float) -> int:
    url = f"ws://localhost:8000/live?api_key={settings.API_KEY}"
    counts = collections.Counter()
    ids = collections.Counter()
    emotions = collections.Counter()
    attentions = []
    confidences = []
    switches = 0
    prev_names = None

    async with websockets.connect(url, max_size=4 * 1024 * 1024) as ws:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + seconds
        while loop.time() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(
                    ws.recv(), timeout=max(1.0, deadline - loop.time())))
            except asyncio.TimeoutError:
                break
            counts[msg["type"]] += 1
            if msg["type"] != "analytics":
                continue
            present = [s for s in msg["students"] if s["present"]]
            names = frozenset(s["name"] for s in present)
            for s in present:
                ids[s["name"]] += 1
                emotions[s["emotion"]] += 1
                attentions.append(s["attention"])
                if isinstance(s.get("identity_confidence"), (int, float)):
                    confidences.append(s["identity_confidence"])
            if prev_names and names and names != prev_names:
                switches += 1
            prev_names = names or prev_names

    print(f"observed {seconds:.0f}s | messages: {dict(counts)}")
    print(f"identities: {dict(ids)} | switches during presence: {switches}")
    print(f"emotions: {dict(emotions)}")
    if attentions:
        print("attention: min=%.2f avg=%.2f max=%.2f"
              % (min(attentions), sum(attentions) / len(attentions), max(attentions)))
    if confidences:
        print("identity confidence: min=%.3f avg=%.3f"
              % (min(confidences), sum(confidences) / len(confidences)))
    return 0


if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    sys.exit(asyncio.run(main(duration)))
