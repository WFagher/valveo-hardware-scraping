from __future__ import annotations

from engine.compare.shortlist import build_shortlist, segment_of, tags_of
from engine.models import ApiType, Controller, Programmability, RebrandPath

REQUIREMENTS = {
    "hard": {
        "cellular": "required",
        "api": ["native_mqtt", "rest_http"],
        "programmability": ["config_only", "rules_engine"],
        "relay_min": 1,
    }
}
WEIGHTS = {
    "rebrandability": 0.30,
    "ready_to_install": 0.20,
    "spec_fit": 0.25,
    "ce_red": 0.15,
    "commercial": 0.10,
}


def _passing(vendor, *, oem=RebrandPath.none, rs485=False):
    c = Controller(
        vendor=vendor,
        model="M",
        cellular=True,
        api_type=ApiType.native_mqtt,
        programmability=Programmability.rules_engine,
        rebrand_path=oem,
    )
    c.lock.relay_count = 2
    c.reader.rs485 = rs485
    return c


def test_segment_and_tags():
    reader = _passing("A", rs485=True)
    assert segment_of(reader) == "reader-capable"
    assert segment_of(_passing("B")) == "relay-only"
    reader.lock.relay_count = 4
    assert "multi-door" in tags_of(reader)


def test_build_shortlist_filters_and_ranks():
    high = _passing("High", oem=RebrandPath.oem_program, rs485=True)
    low = _passing("Low", oem=RebrandPath.none)
    failing = Controller(vendor="Fail", model="Z", cellular=False)
    ranked = build_shortlist([low, failing, high], REQUIREMENTS, WEIGHTS)
    assert [s.controller.vendor for s in ranked] == ["High", "Low"]
    assert ranked[0].score >= ranked[1].score
