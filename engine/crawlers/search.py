"""Keyless web search via DuckDuckGo's HTML endpoint."""
from __future__ import annotations

import re
import urllib.parse

import httpx

_LINK = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"')
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _decode(href: str) -> str:
    if "uddg=" in href:
        url = href if href.startswith("http") else "https:" + href
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "uddg" in params:
            return urllib.parse.unquote(params["uddg"][0])
    if href.startswith("//"):
        return "https:" + href
    return href


def web_search(query: str, *, max_results: int = 5, client: httpx.Client | None = None) -> list[str]:
    owns = client is None
    client = client or httpx.Client(
        timeout=30.0, follow_redirects=True, headers={"User-Agent": _UA}
    )
    try:
        # DuckDuckGo's HTML endpoint answers POST (GET returns a 202 challenge).
        resp = client.post("https://html.duckduckgo.com/html/", data={"q": query})
        resp.raise_for_status()
        urls: list[str] = []
        for href in _LINK.findall(resp.text):
            url = _decode(href)
            if url.startswith("http") and url not in urls:
                urls.append(url)
            if len(urls) >= max_results:
                break
        return urls
    except Exception:
        return []
    finally:
        if owns:
            client.close()
