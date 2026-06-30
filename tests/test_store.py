from __future__ import annotations

from engine.models import ApiType, Controller
from engine.store import DeviceStore


def test_upsert_get_count_dedup(tmp_path):
    store = DeviceStore(tmp_path / "devices.sqlite3")
    try:
        store.upsert(Controller(vendor="Milesight", model="UC300-L05EU", cellular=True))
        assert store.count() == 1
        got = store.get("milesight::uc300-l05eu")
        assert got is not None and got.cellular is True

        # upsert same key updates, does not duplicate
        store.upsert(
            Controller(
                vendor="Milesight",
                model="UC300-L05EU",
                cellular=True,
                api_type=ApiType.native_mqtt,
            )
        )
        assert store.count() == 1
        assert store.get("milesight::uc300-l05eu").api_type is ApiType.native_mqtt

        store.upsert(Controller(vendor="Teracom", model="TCG120-4"))
        assert store.count() == 2
        assert {c.vendor for c in store.all()} == {"Milesight", "Teracom"}
    finally:
        store.close()


def test_get_missing_returns_none(tmp_path):
    store = DeviceStore(tmp_path / "devices.sqlite3")
    try:
        assert store.get("nope::nope") is None
    finally:
        store.close()


def test_seen_tracking(tmp_path):
    store = DeviceStore(tmp_path / "devices.sqlite3")
    try:
        assert store.is_seen("http://x") is False
        store.mark_seen("http://x")
        store.mark_seen("http://x")  # idempotent
        assert store.is_seen("http://x") is True
        assert store.seen_count() == 1
    finally:
        store.close()


def test_store_uses_wal_mode(tmp_path):
    store = DeviceStore(tmp_path / "devices.sqlite3")
    try:
        mode = store.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        store.close()
