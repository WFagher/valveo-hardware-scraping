from __future__ import annotations

from engine.models import ApiType, Controller, Programmability, RebrandPath
from engine.scoring.rules import passes_hard_filters, score_controller

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


def _good():
    c = Controller(
        vendor="Milesight",
        model="UC300-L05EU",
        cellular=True,
        api_type=ApiType.native_mqtt,
        programmability=Programmability.rules_engine,
        rebrand_path=RebrandPath.oem_program,
    )
    c.lock.relay_count = 2
    c.cert.ce = True
    c.cert.red = True
    return c


def test_good_controller_passes():
    ok, reasons = passes_hard_filters(_good(), REQUIREMENTS)
    assert ok is True and reasons == []


def test_no_cellular_fails():
    c = _good()
    c.cellular = False
    ok, reasons = passes_hard_filters(c, REQUIREMENTS)
    assert ok is False and any("cellular" in r for r in reasons)


def test_vendor_cloud_only_fails():
    c = _good()
    c.api_type = ApiType.vendor_cloud_only
    ok, reasons = passes_hard_filters(c, REQUIREMENTS)
    assert ok is False and any("api" in r for r in reasons)


def test_no_relay_fails():
    c = _good()
    c.lock.relay_count = None
    ok, reasons = passes_hard_filters(c, REQUIREMENTS)
    assert ok is False and any("relay" in r for r in reasons)


def test_score_in_range_and_rewards_quality():
    bare = Controller(vendor="X", model="Y")
    assert 0.0 <= score_controller(bare, WEIGHTS) <= 1.0
    assert score_controller(_good(), WEIGHTS) > score_controller(bare, WEIGHTS)
