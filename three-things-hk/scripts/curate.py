"""
curate.py — Claude pre-filters data/events.json into data/shortlist.json

The machine shortlists and drafts. The editor decides.
Requires ANTHROPIC_API_KEY in the environment (GitHub Actions secret).

    python scripts/curate.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-5"

CURATION_PROMPT = """You are the pre-filter for "Three Things — Hong Kong", a weekly \
English-language cultural brief that interprets Hong Kong for an international audience \
of people who work in culture: fashion, art, design, media, luxury.

You will receive a raw list of events scraped from Hong Kong venues. Select up to 15 \
candidates and draft a one-line blurb for each. A human editor picks the final three; \
your job is a clean, honest shortlist.

SELECT FOR
- Curatorial intent: someone made a real editorial or artistic decision
- Specificity to Hong Kong: it could not happen the same way elsewhere, or it reads \
Hong Kong's position between worlds
- Relevance to people who think about culture professionally

REJECT
- Mall activations, generic festivals, anything that exists mainly to drive footfall
- Tourist-board energy
- Events whose description is pure marketing with no discernible content

BLURB VOICE
- One sentence, max 30 words. Dry, precise, knowing. Business of Fashion meets Monocle.
- No exclamation marks. No "must-see", "stunning", "immersive", "don't miss".
- State what it actually is and why a serious person would go.

Respond ONLY with a JSON array, no markdown fences, in this shape:
[{"title": "...", "venue": "...", "url": "...", "dates": "...", "blurb": "...", \
"why_shortlisted": "one short phrase"}]
If fewer than 15 events qualify, return fewer. Quality over count."""


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set")

    events_path = ROOT / "data" / "events.json"
    if not events_path.exists():
        sys.exit("data/events.json missing — run scripts/fetch.py first")

    with open(events_path) as f:
        raw = json.load(f)

    if not raw["events"]:
        sys.exit("No events fetched; nothing to curate")

    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 4000,
            "system": CURATION_PROMPT,
            "messages": [{
                "role": "user",
                "content": json.dumps(raw["events"], ensure_ascii=False),
            }],
        },
        timeout=120,
    )
    resp.raise_for_status()
    text = "".join(
        block.get("text", "") for block in resp.json()["content"]
        if block.get("type") == "text"
    ).strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    shortlist = json.loads(text)

    out = {
        "curated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": shortlist,
    }
    with open(ROOT / "data" / "shortlist.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(shortlist)} candidates → data/shortlist.json")
    print("Editor: pick three, write/adjust blurbs, update site/picks.json")


if __name__ == "__main__":
    main()
