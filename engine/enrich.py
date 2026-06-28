"""Per-device enrichment: fill OEM/CE/origin/rebrand from cited web sources."""
from __future__ import annotations

from collections.abc import Callable

from .crawlers.fetcher import fetch_text
from .crawlers.search import web_search
from .extractors.enrich_extractor import extract_enrichment
from .models import Controller, RebrandPath

_VALID_REBRAND = {e.value for e in RebrandPath}


def _is_relevant(text: str, c: Controller) -> bool:
    """A source is only trustworthy for THIS device if it actually names the
    vendor or model. Drops generic 'what is white-label' blog posts."""
    low = text.lower()
    model_l = c.model.lower()
    token = model_l.split()[0] if model_l.split() else model_l
    return c.vendor.lower() in low or model_l in low or (len(token) >= 4 and token in low)


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
    # A confirmed OEM/white-label program implies the oem_program rebrand path.
    if data["oem"].get("offered") is True and data.get("rebrand_path") == "unknown":
        data["rebrand_path"] = "oem_program"

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
    for url in urls[: max_pages * 2]:
        try:
            text = fetch(url)
        except Exception:
            continue
        if _is_relevant(text, c):  # only trust pages that name this device
            texts.append((url, text))
        if len(texts) >= max_pages:
            break
    if not texts:
        return c

    combined = "\n\n".join(t for _, t in texts)
    enr = extract_enrichment(combined, ollama=ollama, model=model)
    return _merge(c, enr, [u for u, _ in texts])
