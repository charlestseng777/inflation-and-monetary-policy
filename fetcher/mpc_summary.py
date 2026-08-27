"""
The Bank of England's own "Monetary Policy Summary" for each MPC meeting --
the few paragraphs of plain-English reasoning published alongside the
numbered minutes -- scraped verbatim from bankofengland.co.uk. No LLM is
involved: this is the Bank's published text, copied as-is, not a generated
summary.

Page layout (stable since the Summary-and-minutes format was introduced):

    https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/{year}/{month-name}-{year}

    <section class="page-section">
      <h2>Monetary Policy Summary, {Month Year}</h2>
      <p>...</p>
      <p>...</p>
      ...
    </section>
    <h2>Minutes of the Monetary Policy Committee meeting ending on ...</h2>
    ...
"""

from __future__ import annotations

import datetime as dt
import html as html_lib
import re

_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

_H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.S | re.I)
_PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def summary_url(base: str, meeting_date: str) -> str:
    """The Bank's Summary-and-minutes page for the meeting ending on `meeting_date`."""
    when = dt.date.fromisoformat(meeting_date)
    return f"{base}/{when.year}/{_MONTHS[when.month - 1]}-{when.year}"


def _clean(fragment: str) -> str:
    text = _TAG_RE.sub("", fragment)
    text = html_lib.unescape(text)
    return " ".join(text.split())


def parse_summary_page(html: str) -> dict | None:
    """
    Pull the "Monetary Policy Summary" heading and its paragraphs out of a
    meeting page. Returns None if the page doesn't have the expected section --
    meetings before ~August 2021 were published as PDF only, with no HTML
    rendition of the text to scrape, and a handful of pages wrap the heading
    text in an inline tag (e.g. <h2><strong>...</strong></h2>), which is why
    this matches on any <h2> and cleans it rather than anchoring the regex to
    the heading's exact inner markup.
    """
    heading_match = None
    for match in _H2_RE.finditer(html):
        if _clean(match.group(1)).lower().startswith("monetary policy summary"):
            heading_match = match
            break
    if heading_match is None:
        return None

    next_heading = html.find("<h2", heading_match.end())
    section = html[heading_match.end():next_heading if next_heading != -1 else heading_match.end() + 20000]

    paragraphs = [_clean(match.group(1)) for match in _PARA_RE.finditer(section)]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        return None

    return {"heading": _clean(heading_match.group(1)), "paragraphs": paragraphs}
