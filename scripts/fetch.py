"""
fetch.py — pull raw event data from sources.yaml into data/events.json

Designed to degrade gracefully: a source that fails is logged and skipped,
never fatal. Run daily by GitHub Actions, or locally:

    pip install -r requirements.txt
    python scripts/fetch.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
HEADERS = {
    "User-Agent": "ThreeThingsHK/0.1 (cultural calendar; contact via repo issues)"
}
TIMEOUT = 20


def load_sources():
    with open(ROOT / "sources.yaml") as f:
        return yaml.safe_load(f)["sources"]


def fetch_jsonld(source):
    """Extract schema.org Event objects embedded in a page."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_jsonld(payload):
            ev = _normalise_jsonld_event(item, source)
            if ev:
                events.append(ev)
    return events


def _walk_jsonld(payload):
    """Yield every dict that looks like an Event, however nested."""
    if isinstance(payload, dict):
        t = payload.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if any("Event" in str(x) for x in types):
            yield payload
        for v in payload.values():
            yield from _walk_jsonld(v)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_jsonld(item)


def _normalise_jsonld_event(item, source):
    name = item.get("name")
    if not name:
        return None
    return {
        "title": str(name).strip(),
        "url": item.get("url") or source["url"],
        "start": item.get("startDate"),
        "end": item.get("endDate"),
        "description": _clean(item.get("description", ""))[:600],
        "venue": source["venue"],
        "source": source["name"],
    }


def fetch_ics(source):
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    events, current = [], None
    for line in resp.text.splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if current.get("SUMMARY"):
                events.append({
                    "title": current.get("SUMMARY", ""),
                    "url": current.get("URL", source["url"]),
                    "start": current.get("DTSTART", ""),
                    "end": current.get("DTEND", ""),
                    "description": _clean(current.get("DESCRIPTION", ""))[:600],
                    "venue": source["venue"],
                    "source": source["name"],
                })
            current = None
        elif current is not None and ":" in line:
            key, _, value = line.partition(":")
            current[key.split(";")[0]] = value
    return events


def fetch_rss(source):
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "xml")
    events = []
    for item in soup.find_all("item"):
        title = item.title.get_text(strip=True) if item.title else None
        if not title:
            continue
        events.append({
            "title": title,
            "url": item.link.get_text(strip=True) if item.link else source["url"],
            "start": item.pubDate.get_text(strip=True) if item.pubDate else "",
            "end": "",
            "description": _clean(
                item.description.get_text(strip=True) if item.description else ""
            )[:600],
            "venue": source["venue"],
            "source": source["name"],
        })
    return events


def fetch_taikwun(source):
    """Tai Kwun ships programme cards as static HTML: <a class='programme-block'>."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    for block in soup.find_all("a", class_="programme-block"):
        title_tag = block.find("h2")
        if not title_tag:
            continue
        date_tag = block.find("span", class_="time")
        venue_tag = block.find_all("span", class_="venue")
        venue_text = venue_tag[0].get_text(" ", strip=True) if venue_tag else ""
        events.append({
            "title": title_tag.get_text(strip=True),
            "url": block.get("href", source["url"]),
            "start": date_tag.get_text(" ", strip=True) if date_tag else "",
            "end": "",
            "description": "",
            "venue": f"{source['venue']} — {venue_text}" if venue_text else source["venue"],
            "source": source["name"],
        })
    return events


def fetch_hkpm(source):
    """HKPM embeds event data as `eventData['<cat>'] = [...]` in an inline script."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    events = []
    for match in re.finditer(r"eventData\[['\"]\w+['\"]\]\s*=\s*(\[.*?\]);", resp.text):
        try:
            items = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        for item in items:
            title = item.get("title")
            if not title:
                continue
            events.append({
                "title": title.strip(),
                "url": item.get("url") or source["url"],
                "start": item.get("start", ""),
                "end": item.get("end", ""),
                "description": _clean(item.get("desc", ""))[:600],
                "venue": source["venue"],
                "source": source["name"],
            })
    return events


def fetch_hkma(source):
    """HK Museum of Art ships <li class='event-item'> cards with data-start/data-end."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    for li in soup.find_all("li", class_="event-item"):
        title_tag = li.find(class_="h3")
        if not title_tag:
            continue
        link = li.find("a", href=True)
        href = link["href"] if link else source["url"]
        if href.startswith("/"):
            href = "https://hk.art.museum" + href
        events.append({
            "title": title_tag.get_text(strip=True),
            "url": href,
            "start": li.get("data-start", ""),
            "end": li.get("data-end", ""),
            "description": "",
            "venue": source["venue"],
            "source": source["name"],
        })
    return events


def _clean(text):
    return re.sub(r"<[^>]+>", " ", re.sub(r"\s+", " ", str(text))).strip()


FETCHERS = {
    "jsonld": fetch_jsonld,
    "ics": fetch_ics,
    "rss": fetch_rss,
    "taikwun": fetch_taikwun,
    "hkpm": fetch_hkpm,
    "hkma": fetch_hkma,
}


def main():
    all_events, failures = [], []
    for source in load_sources():
        try:
            got = FETCHERS[source["type"]](source)
            print(f"[ok]   {source['name']}: {len(got)} events")
            all_events.extend(got)
        except Exception as exc:  # noqa: BLE001 — a dead source must not kill the run
            print(f"[fail] {source['name']}: {exc}", file=sys.stderr)
            failures.append(source["name"])

    # de-duplicate on (title, venue)
    seen, unique = set(), []
    for ev in all_events:
        key = (ev["title"].lower(), ev["venue"])
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "events": unique,
    }
    (ROOT / "data").mkdir(exist_ok=True)
    with open(ROOT / "data" / "events.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(unique)} unique events → data/events.json")


if __name__ == "__main__":
    main()
