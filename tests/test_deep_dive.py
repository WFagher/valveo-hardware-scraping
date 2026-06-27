from __future__ import annotations

import json

from engine.drafters.deep_dive import (
    criteria_fit_rows,
    generate_analysis,
    render_deep_dive,
    variant_warning,
)
from engine.models import ApiType, Controller, Programmability, RebrandPath

REQ = {
    "hard": {
        "cellular": "required",
        "api": ["native_mqtt", "rest_http"],
        "programmability": ["config_only", "rules_engine"],
        "relay_min": 1,
    }
}


def _uc300():
    c = Controller(
        vendor="Milesight",
        model="UC300-L05EU",
        sku="UC300-L05EU",
        country_of_origin="China",
        cellular=True,
        cellular_tech="LTE Cat 1",
        api_type=ApiType.native_mqtt,
        programmability=Programmability.rules_engine,
        own_broker=True,
        digital_inputs=4,
        ip_rating="IP30",
        price_eur=189.9,
        rebrand_path=RebrandPath.oem_program,
    )
    c.lock.relay_count = 2
    c.reader.rs485 = True
    c.cert.ce = True
    c.cert.red = True
    return c


class FakeOllama:
    def __init__(self, resp):
        self.resp = resp

    def chat(self, model, messages, **kw):
        return self.resp


def test_variant_warning_uc300():
    assert "868M" in variant_warning(_uc300())
    assert variant_warning(Controller(vendor="X", model="Y")) is None


def test_criteria_fit_rows_mark_hard_met():
    rows = {label: status for label, status, _ in criteria_fit_rows(_uc300(), REQ)}
    assert rows["LTE / 4G cellular (required)"] == "yes"
    assert rows["No firmware / config-only (required)"] == "yes"
    assert rows["Relay output (required)"] == "yes"


def test_unconfirmed_bonus_is_unknown_not_no():
    # a controller with no extracted CE/WiFi data shows ❓ (unknown), never ❌
    bare = Controller(vendor="V", model="M", cellular=True)
    rows = {label: status for label, status, _ in criteria_fit_rows(bare, REQ)}
    assert rows["CE + RED (bonus)"] == "unknown"
    assert rows["WiFi (bonus)"] == "unknown"


def test_generate_analysis_parses_json():
    resp = json.dumps(
        {
            "scenarios": [{"title": "Door", "body": "x"}],
            "limitations": [{"severity": "high", "text": "no wifi"}],
            "mitigations": [{"limitation": "no wifi", "solution": "ble reader"}],
            "verdict": "great indoor pick",
        }
    )
    a = generate_analysis(_uc300(), ollama=FakeOllama(resp), model="m")
    assert a["scenarios"][0]["title"] == "Door"
    assert a["verdict"] == "great indoor pick"


def test_generate_analysis_bad_json_defaults():
    a = generate_analysis(_uc300(), ollama=FakeOllama("not json"), model="m")
    assert a["scenarios"] == [] and a["verdict"] == ""


def test_render_contains_sections():
    analysis = {
        "scenarios": [{"title": "Supervised door", "body": "open + sensors"}],
        "limitations": [{"severity": "high", "text": "no offline cache"}],
        "mitigations": [{"limitation": "no offline cache", "solution": "edge companion"}],
        "verdict": "Strongest indoor pick.",
    }
    md = render_deep_dive(_uc300(), REQ, analysis)
    assert "# Milesight UC300-L05EU" in md
    assert "868M" in md
    assert "Supervised door" in md
    assert "no offline cache" in md
    assert "Strongest indoor pick." in md
    assert "189.9" in md
