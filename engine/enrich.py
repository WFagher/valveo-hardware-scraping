"""Per-device enrichment: fill OEM/CE/origin/rebrand from cited web sources."""
from __future__ import annotations

from collections.abc import Callable

from .crawlers.fetcher import fetch_text
from .crawlers.search import web_search
from .extractors.enrich_extractor import extract_enrichment
from .models import Controller, RebrandPath

_VALID_REBRAND = {e.value for e in RebrandPath}


def _queries(c: Controller) -> list[str]:
    base = f"{c.vendor} {c.model}"
    return [
        f"{base} OEM white label private label",
        f"{base} CE RED declaration of conformity",
        f"{c.vendor} company country headquarters",
    ]


def _merge(c: Controller, enr: dict, sources: list[str]) -> Controller:
    data = c.model_dump()

    if data.get("country_of_origin") is None and enr.get("country_of_origin"):
        data["country_of_origin"] = enr["country_of_origin"]

    cert = data["cert"]
    for key in ("ce", "red"):
        if cert.get(key) is None and enr.get(key) is not None:
            cert[key] = enr[key]

    oem = data["oem"]
    if oem.get("offered") is None and enr.get("oem_offered") is not None:
        oem["offered"] = enr["oem_offered"]
    if oem.get("moq") is None and enr.get("oem_moq") is not None:
        oem["moq"] = enr["oem_moq"]

    if data.get("rebrand_path") == "unknown" and enr.get("rebrand_path") in _VALID_REBRAND:
        data["rebrand_path"] = enr["rebrand_path"]

    srcs = data.get("sources") or []
    for s in sources:
        if s not in srcs:
            srcs.append(s)
    data["sources"] = srcs

    return Controller.model_validate(data)


def enrich_controller(
    c: Controller,
    *,
    ollama,
    model: str,
    searcher: Callable[..., list[str]] = web_search,
    fetch: Callable[..., str] = fetch_text,
    max_pages: int = 3,
) -> Controller:
    urls: list[str] = []
    for query in _queries(c):
        try:
            for url in searcher(query, max_results=2):
                if url not in urls:
                    urls.append(url)
        except Exception:
            continue

    texts: list[tuple[str, str]] = []
    for url in urls[:max_pages]:
        try:
            texts.append((url, fetch(url)))
        except Exception:
            continue
    if not texts:
        return c

    combined = "\n\n".join(t for _, t in texts)
    enr = extract_enrichment(combined, ollama=ollama, model=model)
    return _merge(c, enr, [u for u, _ in texts])
