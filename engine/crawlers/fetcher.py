"""Fetch a URL and reduce it to plain text for LLM extraction."""
from __future__ import annotations

import re

import httpx

_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(html: str) -> str:
    text = _SCRIPT.sub(" ", html)
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


def fetch_text(url: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> str:
    owns = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return strip_html(resp.text)
    finally:
        if owns:
            client.close()
