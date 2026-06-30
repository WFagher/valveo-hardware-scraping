from __future__ import annotations

from engine.crawlers.discovery import _is_junk, prospect_urls


def test_is_junk_filters_known_domains():
    assert _is_junk("https://en.wikipedia.org/wiki/MQTT") is True
    assert _is_junk("https://www.youtube.com/watch?v=x") is True
    assert _is_junk("https://www.bliiot.com/products/rtu5022") is False
    assert _is_junk("https://milesight.com/iot/uc300") is False


def test_prospect_dedupes_junk_and_seen():
    def fake_search(query, max_results=5):
        return [
            "https://bliiot.com/rtu5022",
            "https://en.wikipedia.org/wiki/Relay",  # junk
            "https://bliiot.com/rtu5022",  # dup
            "https://teracom.com/already-seen",
        ]

    seen = {"https://teracom.com/already-seen"}
    out = prospect_urls(
        ["q1", "q2"], searcher=fake_search, is_seen=lambda u: u in seen
    )
    assert out == ["https://bliiot.com/rtu5022"]  # junk, dup, and seen removed


def test_prospect_survives_search_error():
    def boom(query, max_results=5):
        raise RuntimeError("network")

    assert prospect_urls(["q"], searcher=boom) == []
