"""Open-ended discovery: search the web for NEW candidate device pages."""
from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from pathlib import Path

import yaml

from .search import web_search

# Domains that never host a manufacturer product page worth extracting.
_JUNK_DOMAINS = {
    "wikipedia.org", "youtube.com", "youtu.be", "reddit.com", "quora.com",
    "medium.com", "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "pinterest.com", "instagram.com", "ebay.com", "glassdoor.com", "indeed.com",
    "tiktok.com", "yelp.com",
}


def _is_junk(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in _JUNK_DOMAINS)


def load_queries(config_dir: Path) -> list[str]:
    path = config_dir / "discovery_queries.yaml"
    if not path.is_file():
        return []
    return yaml.safe_load(path.read_text()).get("queries", [])


def prospect_urls(
    queries: list[str],
    *,
    searcher: Callable[..., list[str]] = web_search,
    max_per_query: int = 5,
    is_seen: Callable[[str], bool] = lambda _u: False,
) -> list[str]:
    """Run each query, returning de-duplicated, non-junk, unseen candidate URLs."""
    found: list[str] = []
    for query in queries:
        try:
            results = searcher(query, max_results=max_per_query)
        except Exception:
            continue
        for url in results:
            if url in found or _is_junk(url) or is_seen(url):
                continue
            found.append(url)
    return found
