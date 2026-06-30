from __future__ import annotations

import json

from engine.enrich import enrich_controller
from engine.extractors.enrich_extractor import extract_enrichment
from engine.models import ApiType, Controller, RebrandPath


class FakeOllama:
    def __init__(self, resp):
        self.resp = resp

    def chat(self, model, messages, **kw):
        return self.resp


def _accept_all(claims, source, **kw):
    return {k: True for k in claims}


def test_extract_enrichment_parses():
    resp = json.dumps({"country_of_origin": "Bulgaria", "ce": True, "red": True})
    d = extract_enrichment("t", ollama=FakeOllama(resp), model="m")
    assert d["country_of_origin"] == "Bulgaria" and d["ce"] is True


def test_extract_enrichment_bad_json():
    assert extract_enrichment("t", ollama=FakeOllama("nope"), model="m") == {}


def test_enrich_fills_unknown_fields_and_records_sources():
    c = Controller(vendor="Teracom", model="TCG120-4", cellular=True)
    resp = json.dumps(
        {"country_of_origin": "Bulgaria", "ce": True, "red": True,
         "oem_offered": True, "rebrand_path": "oem_program"}
    )
    out = enrich_controller(
        c, ollama=FakeOllama(resp), model="m",
        searcher=lambda q, **k: ["https://teracomsystems.com/about"],
        fetch=lambda u, **k: "Teracom is based in Bulgaria, CE/RED certified, OEM available.",
        verifier=_accept_all,
    )
    assert out.country_of_origin == "Bulgaria"
    assert out.cert.ce is True and out.cert.red is True
    assert out.oem.offered is True
    assert out.rebrand_path is RebrandPath.oem_program
    assert "https://teracomsystems.com/about" in out.sources


def test_enrich_does_not_overwrite_existing():
    c = Controller(vendor="V", model="M", country_of_origin="China", api_type=ApiType.native_mqtt)
    resp = json.dumps({"country_of_origin": "Bulgaria"})
    out = enrich_controller(
        c, ollama=FakeOllama(resp), model="m",
        searcher=lambda q, **k: ["https://src/1"],
        fetch=lambda u, **k: "V M product page with details.",
        verifier=_accept_all,
    )
    assert out.country_of_origin == "China"  # not overwritten
    assert out.api_type is ApiType.native_mqtt


def test_enrich_skips_irrelevant_pages():
    # a generic blog that doesn't name the device must not produce claims
    c = Controller(vendor="Teracom", model="TCG120-4")
    resp = json.dumps({"oem_offered": True, "rebrand_path": "oem_program"})
    out = enrich_controller(
        c, ollama=FakeOllama(resp), model="m",
        searcher=lambda q, **k: ["https://generic/blog"],
        fetch=lambda u, **k: "A general article about private label manufacturing strategies.",
    )
    assert out.oem.offered is None  # irrelevant source not applied
    assert out == c


def test_oem_offered_implies_oem_program_rebrand():
    c = Controller(vendor="BLIIoT", model="RTU5022")
    resp = json.dumps({"oem_offered": True})
    out = enrich_controller(
        c, ollama=FakeOllama(resp), model="m",
        searcher=lambda q, **k: ["https://bliiot.com/rtu5022"],
        fetch=lambda u, **k: "BLIIoT RTU5022 — OEM and ODM services available.",
        verifier=_accept_all,
    )
    assert out.oem.offered is True
    assert out.rebrand_path is RebrandPath.oem_program


def test_origin_dropped_when_only_reseller_source():
    # origin claim from a non-vendor (reseller) domain must be dropped
    c = Controller(vendor="Milesight", model="UC300")
    resp = json.dumps({"country_of_origin": "US"})
    out = enrich_controller(
        c, ollama=FakeOllama(resp), model="m",
        searcher=lambda q, **k: ["https://iotnvr.com/milesight-uc300"],
        fetch=lambda u, **k: "Milesight UC300 — buying from US?",
        verifier=_accept_all,
    )
    assert out.country_of_origin is None


def test_origin_kept_from_vendor_domain():
    c = Controller(vendor="BLIIoT", model="RTU5022")
    resp = json.dumps({"country_of_origin": "China"})
    out = enrich_controller(
        c, ollama=FakeOllama(resp), model="m",
        searcher=lambda q, **k: ["https://www.bliiot.com/about-us"],
        fetch=lambda u, **k: "BLIIoT RTU5022 — headquartered in China.",
        verifier=_accept_all,
    )
    assert out.country_of_origin == "China"


def test_verification_drops_unsupported_claim():
    # the extractor proposes OEM, but verification refutes it -> not applied
    c = Controller(vendor="BLIIoT", model="RTU5022")
    resp = json.dumps({"oem_offered": True})
    out = enrich_controller(
        c, ollama=FakeOllama(resp), model="m",
        searcher=lambda q, **k: ["https://bliiot.com/rtu5022"],
        fetch=lambda u, **k: "BLIIoT RTU5022 datasheet — relay outputs, cellular.",
        verifier=lambda claims, source, **k: {key: False for key in claims},
    )
    assert out.oem.offered is None
    assert out.rebrand_path is RebrandPath.unknown


def test_enrich_no_results_returns_unchanged():
    c = Controller(vendor="V", model="M")
    out = enrich_controller(
        c, ollama=FakeOllama("{}"), model="m",
        searcher=lambda q, **k: [],
        fetch=lambda u, **k: "text",
    )
    assert out == c
