from __future__ import annotations

import json

from engine.extractors.spec_extractor import build_messages, extract_controller


class FakeOllama:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def chat(self, model, messages, **kw):
        self.calls += 1
        return self.response


def test_build_messages_has_system_and_user():
    msgs = build_messages("UC300 4G LTE MQTT")
    assert msgs[0].role == "system" and "never invent" in msgs[0].content.lower()
    assert "UC300 4G LTE MQTT" in msgs[-1].content


def test_extract_valid_record():
    resp = json.dumps(
        {
            "vendor": "Milesight",
            "model": "UC300-L05EU",
            "cellular": True,
            "api_type": "native_mqtt",
            "lock": {"relay_count": 2},
            "reader": {"rs485": True},
            "cert": {"ce": True, "red": True},
        }
    )
    c = extract_controller(
        "...", ollama=FakeOllama(resp), model="m", source_url="https://x/uc300"
    )
    assert c is not None
    assert c.vendor == "Milesight" and c.lock.relay_count == 2
    assert c.reader.rs485 is True and c.api_type.value == "native_mqtt"
    assert "https://x/uc300" in c.sources


def test_extract_strips_code_fences():
    resp = "```json\n" + json.dumps({"vendor": "Teracom", "model": "TCG120-4"}) + "\n```"
    c = extract_controller("t", ollama=FakeOllama(resp), model="m")
    assert c is not None and c.vendor == "Teracom"


def test_extract_missing_vendor_returns_none():
    c = extract_controller("t", ollama=FakeOllama(json.dumps({"model": "X"})), model="m")
    assert c is None


def test_extract_bad_json_returns_none():
    assert extract_controller("t", ollama=FakeOllama("not json"), model="m") is None


def test_extract_coerces_optionlist_enum():
    # the model sometimes echoes the option list instead of picking one
    resp = json.dumps(
        {"vendor": "Teracom", "model": "TCG120-4", "api_type": "native_mqtt|rest_http",
         "programmability": "config_only|rules_engine"}
    )
    c = extract_controller("t", ollama=FakeOllama(resp), model="m")
    assert c is not None
    assert c.api_type.value == "native_mqtt"
    assert c.programmability.value == "config_only"


def test_infer_api_type_from_protocols():
    resp = json.dumps(
        {"vendor": "Milesight", "model": "UC300", "api_type": "unknown",
         "protocols": ["TCP", "UDP", "MQTT", "SMS"]}
    )
    c = extract_controller("t", ollama=FakeOllama(resp), model="m")
    assert c is not None and c.api_type.value == "native_mqtt"


def test_extract_salvages_bad_field():
    # one malformed field must not discard the whole device
    resp = json.dumps(
        {"vendor": "Milesight", "model": "UC300", "cellular": True,
         "digital_inputs": "not a number", "lock": {"relay_count": "bad"}}
    )
    c = extract_controller("t", ollama=FakeOllama(resp), model="m")
    assert c is not None
    assert c.vendor == "Milesight" and c.cellular is True
    assert c.digital_inputs is None          # bad field dropped
    assert c.lock.relay_count is None        # bad nested field dropped


def test_extract_truncates_long_text():
    captured = {}

    class Capturing:
        def chat(self, model, messages, **kw):
            captured["len"] = len(messages[-1].content)
            return json.dumps({"vendor": "V", "model": "M"})

    extract_controller("x" * 50000, ollama=Capturing(), model="m")
    assert captured["len"] < 50000  # the page was truncated before prompting
