from __future__ import annotations

from engine.models import ApiType, Controller, Programmability, RebrandPath
from engine.outputs.report import render_report

REQ = {
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


def _passing():
    c = Controller(
        vendor="BLIIoT", model="RTU5022", cellular=True, api_type=ApiType.native_mqtt,
        programmability=Programmability.config_only, country_of_origin="China",
        rebrand_path=RebrandPath.oem_program,
    )
    c.lock.relay_count = 8
    c.oem.offered = True
    return c


def test_render_report_lists_passing_device():
    md = render_report([_passing()], REQ, WEIGHTS, total=1, seen=5, timestamp="2026-06-30T12:00")
    assert "Live shortlist" in md
    assert "Devices evaluated: 1" in md and "pages crawled: 5" in md
    assert "BLIIoT RTU5022" in md
    assert "China" in md  # origin column


def test_render_report_empty():
    md = render_report([], REQ, WEIGHTS, total=0, seen=0)
    assert "No devices pass the hard criteria yet" in md
