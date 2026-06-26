from __future__ import annotations

from pathlib import Path

import pytest

from engine.research_config import load_requirements, load_scoring, load_sources

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def test_load_requirements_has_hard_filters():
    req = load_requirements(CONFIG_DIR)
    assert req["hard"]["cellular"] == "required"
    assert "native_mqtt" in req["hard"]["api"]
    assert req["benchmark"] == "Milesight UC300-L05EU"


def test_load_scoring_weights_sum_to_one():
    w = load_scoring(CONFIG_DIR)["weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_load_sources_has_cellular_tier():
    src = load_sources(CONFIG_DIR)
    assert "Milesight" in src["tiers"]["cellular_iot_controllers"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_requirements(tmp_path)
