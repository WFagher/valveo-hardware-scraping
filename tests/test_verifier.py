from __future__ import annotations

import json

from engine.extractors.verifier import verify_claims


class FakeOllama:
    def __init__(self, resp):
        self.resp = resp

    def chat(self, model, messages, **kw):
        return self.resp


def test_verify_claims_maps_supported():
    resp = json.dumps({"oem_offered": True, "ce": False})
    out = verify_claims(
        {"oem_offered": "vendor offers OEM", "ce": "device is CE marked"},
        "some source text",
        ollama=FakeOllama(resp),
        model="m",
    )
    assert out == {"oem_offered": True, "ce": False}


def test_verify_claims_defaults_missing_to_false():
    resp = json.dumps({"oem_offered": True})  # 'ce' not answered
    out = verify_claims(
        {"oem_offered": "x", "ce": "y"}, "src", ollama=FakeOllama(resp), model="m"
    )
    assert out == {"oem_offered": True, "ce": False}


def test_verify_claims_bad_json_all_false():
    out = verify_claims({"a": "x", "b": "y"}, "src", ollama=FakeOllama("nope"), model="m")
    assert out == {"a": False, "b": False}


def test_verify_claims_empty():
    assert verify_claims({}, "src", ollama=FakeOllama("{}"), model="m") == {}
