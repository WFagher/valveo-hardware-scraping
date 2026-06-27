from __future__ import annotations

from engine.models import ApiType, Controller, Programmability, RebrandPath


def test_controller_defaults_and_key():
    c = Controller(vendor="Milesight", model="UC300-L05EU")
    assert c.key == "milesight::uc300-l05eu"
    assert c.api_type is ApiType.unknown
    assert c.programmability is Programmability.unknown
    assert c.rebrand_path is RebrandPath.unknown
    assert c.wifi is False and c.bluetooth is False
    assert c.reader.rs485 is False
    assert c.buy_links == []


def test_controller_json_roundtrip():
    c = Controller(
        vendor="Milesight",
        model="UC300-L05EU",
        sku="UC300-L05EU",
        cellular=True,
        cellular_tech="LTE Cat 1",
        api_type=ApiType.native_mqtt,
        programmability=Programmability.rules_engine,
        own_broker=True,
        digital_inputs=4,
    )
    c.lock.relay_count = 2
    raw = c.model_dump_json()
    back = Controller.model_validate_json(raw)
    assert back == c
    assert back.lock.relay_count == 2
    assert back.api_type is ApiType.native_mqtt
