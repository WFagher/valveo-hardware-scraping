from __future__ import annotations

import engine


def test_version_present():
    assert isinstance(engine.__version__, str)
    assert engine.__version__
