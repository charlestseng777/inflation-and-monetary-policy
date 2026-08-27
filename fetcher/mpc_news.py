"""
Recent news coverage of each sitting MPC member, from Google News' public RSS
search (no API key, no scraping of Google's actual search UI -- this is a
documented, stable RSS endpoint). One query per member, by name, most recent
items first.

Google News RSS wraps the true article URL behind a news.google.com redirect
link; that's still a working, clickable link to the original piece, just not
the publisher's own URL directly.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import urllib.parse
import xml.etree.ElementTree as ET


def member_names(decisions: list[dict]) -> list[str]:
    """Every name that sat on the most recent decision -- the current Committee."""
    if not decisions:
        return []
    latest = decisions[-1]
    names = {entry["name"] for entry in latest["members"] + latest["hawks"] + latest["doves"]}
    return sorted(names)


def search_url(base: str, name: str) -> str:
    query = f'"{name}" Bank of England'
    return f"{base}?{urllib.parse.urlencode({'q': query, 'hl': 'en-GB', 'gl': 'GB', 'ceid': 'GB:en'})}"


def _parse_pub_date(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return email.utils.parsedate_to_datetime(text).astimezone(dt.timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def parse_news_feed(xml_bytes: bytes, limit: int = 5) -> list[dict]:
    """The `limit` most recent items from a Google News RSS response."""
    root = ET.fromstring(xml_bytes)
    items = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = _parse_pub_date(item.findtext("pubDate"))
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None and source_el.text else None

        if not title or not link:
            continue
        # The feed appends " - <source>" to every title; drop it since source
        # is carried separately and showing it twice reads as a glitch.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()

        items.append({"title": title, "link": link, "source": source, "published": published})

    items.sort(key=lambda entry: entry["published"] or "", reverse=True)
    return items[:limit]
