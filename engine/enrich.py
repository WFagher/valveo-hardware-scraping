"""Per-device enrichment: fill OEM/CE/origin/rebrand from cited web sources."""
from __future__ import annotations

from collections.abc import Callable

from .crawlers.fetcher import fetch_text
from .crawlers.search import web_search
from .extractors.enrich_extractor import extract_enrichment
from .extractors.verifier import verify_claims
from .models import Controller, RebrandPath

_VALID_REBRAND = {e.value for e in RebrandPath}
# Per-page budget so a nav-heavy first page doesn't starve later (CE/about) pages.
_PER_PAGE = 8000


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


def _claim_texts(enr: dict, c: Controller) -> dict[str, str]:
    """Turn candidate enriched values into checkable claim statements."""
    dev = f"{c.vendor} {c.model}"
    claims: dict[str, str] = {}
    if enr.get("country_of_origin"):
        claims["country_of_origin"] = (
            f"The vendor {c.vendor} is based/headquartered in {enr['country_of_origin']}."
        )
    if enr.get("ce") is True:
        claims["ce"] = f"The {dev} is CE marked / CE certified."
    elif enr.get("ce") is False:
        claims["ce"] = f"The source explicitly states the {dev} is NOT CE certified."
    if enr.get("red") is True:
        claims["red"] = f"The {dev} complies with the EU Radio Equipment Directive (RED)."
    elif enr.get("red") is False:
        claims["red"] = f"The source explicitly states the {dev} does NOT comply with RED."
    if enr.get("oem_offered") is True:
        claims["oem_offered"] = (
            f"The vendor {c.vendor} offers OEM / ODM / white-label / private-label services."
        )
    elif enr.get("oem_offered") is False:
        claims["oem_offered"] = f"The source explicitly states {c.vendor} does not offer OEM."
    return claims


def _verify(enr: dict, c: Controller, source: str, *, verifier, ollama, model: str) -> dict:
    """Drop any candidate claim the source does not explicitly support."""
    claims = _claim_texts(enr, c)
    if not claims:
        return enr
    verdicts = verifier(claims, source, ollama=ollama, model=model)
    for key, supported in verdicts.items():
        if not supported:
            enr[key] = None
    return enr


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
    verifier: Callable[..., dict] = verify_claims,
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

    combined = "\n\n".join(t[:_PER_PAGE] for _, t in texts)
    enr = extract_enrichment(combined, ollama=ollama, model=model)
    enr = _verify(enr, c, combined, verifier=verifier, ollama=ollama, model=model)
    return _merge(c, enr, [u for u, _ in texts])
