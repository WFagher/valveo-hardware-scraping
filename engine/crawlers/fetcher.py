"""Fetch a URL as text.

Two flavours, because discovery and enrichment have opposite needs:
- `fetch_text`  → full page (tags stripped, spec TABLES kept) — for spec extraction.
- `fetch_main`  → main content only (nav/footer stripped via readability) — for enrichment.
"""
from __future__ import annotations

import logging
import re

import httpx
from readability import Document

# readability logs full tracebacks to stderr on unparseable pages even though we
# fall back gracefully — silence it so discover/enrich output stays clean.
logging.getLogger("readability").setLevel(logging.CRITICAL)
logging.getLogger("readability.readability").setLevel(logging.CRITICAL)

_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def strip_html(html: str) -> str:
    text = _SCRIPT.sub(" ", html)
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


def extract_main(html: str) -> str:
    """Main article/content text with nav/footer/sidebar stripped (readability).

    Falls back to a plain tag-strip when readability finds too little.
    """
    try:
        main = strip_html(Document(html).summary())
        if len(main) > 200:
            return main
    except Exception:
        pass
    return strip_html(html)


def _get(url: str, client: httpx.Client | None, timeout: float) -> str:
    owns = client is None
    client = client or httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": _UA}
    )
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
    finally:
        if owns:
            client.close()


def fetch_text(url: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> str:
    """Full page text (keeps spec tables) — used for device spec extraction."""
    return strip_html(_get(url, client, timeout))


def fetch_main(url: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> str:
    """Main-content text (nav stripped) — used for enrichment."""
    return extract_main(_get(url, client, timeout))
