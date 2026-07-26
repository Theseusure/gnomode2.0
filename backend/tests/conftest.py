"""Pytest fixtures for gnomode backend tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


@pytest.fixture
def tmp_watch_paths(tmp_path, monkeypatch):
    config_path = tmp_path / "watch.json"
    seen_path = tmp_path / "watch_seen.json"
    from app.config import settings

    monkeypatch.setattr(settings, "watch_config_path", str(config_path))
    monkeypatch.setattr(settings, "watch_seen_path", str(seen_path))
    return config_path, seen_path
