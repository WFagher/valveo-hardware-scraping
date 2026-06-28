"""Fetch a URL and reduce it to the main content text for LLM extraction."""
from __future__ import annotations

import re

import httpx
from readability import Document

_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def strip_html(html: str) -> str:
    text = _SCRIPT.sub(" ", html)
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


def extract_main(html: str) -> str:
    """Main article/content text, with nav/footer/sidebar stripped (readability).

    Falls back to a plain tag-strip when readability finds too little.
    """
    try:
        main = strip_html(Document(html).summary())
        if len(main) > 200:
            return main
    except Exception:
        pass
    return strip_html(html)


def fetch_text(url: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> str:
    owns = client is None
    client = client or httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": _UA}
    )
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return extract_main(resp.text)
    finally:
        if owns:
            client.close()
