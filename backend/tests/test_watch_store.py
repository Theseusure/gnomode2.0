"""Tests for watch config / seen-set persistence and dedup keys."""

from __future__ import annotations

from app.models import WatchConfig, WatchScreenFilters
from app.watch_store import WatchStore, seen_key


def test_seen_key_normalizes():
    assert seen_key(" 0xAbC ", "0xDeF") == "0xabc:0xdef"


def test_config_roundtrip(tmp_path):
    store = WatchStore(
        config_path=tmp_path / "watch.json",
        seen_path=tmp_path / "seen.json",
        state_path=tmp_path / "state.json",
    )
    assert store.load_config().enabled is False

    cfg = WatchConfig(
        enabled=True,
        interval_sec=600,
        max_tokens_per_cycle=5,
        telegram_chat_id="42",
        screen=WatchScreenFilters(min_liq=1000.0),
    )
    store.save_config(cfg)
    loaded = store.load_config()
    assert loaded.enabled is True
    assert loaded.interval_sec == 600
    assert loaded.max_tokens_per_cycle == 5
    assert loaded.telegram_chat_id == "42"
    assert loaded.screen.min_liq == 1000.0


def test_seen_dedup_and_clear(tmp_path):
    store = WatchStore(
        config_path=tmp_path / "watch.json",
        seen_path=tmp_path / "seen.json",
        state_path=tmp_path / "state.json",
    )
    w1, t1 = "0xAAA", "0xTTT"
    w2, t2 = "0xBBB", "0xTTT"

    assert store.is_seen(w1, t1) is False
    assert store.mark_seen([(w1, t1)]) == 1
    assert store.is_seen(w1, t1) is True
    assert store.is_seen(w1.lower(), t1.lower()) is True
    assert store.mark_seen([(w1, t1)]) == 0
    assert store.mark_seen([(w2, t2)]) == 1
    assert store.seen_count() == 2

    # Persist across new store instance
    store2 = WatchStore(
        config_path=tmp_path / "watch.json",
        seen_path=tmp_path / "seen.json",
        state_path=tmp_path / "state.json",
    )
    assert store2.is_seen(w1, t1) is True
    assert store2.seen_count() == 2

    store2.clear_seen()
    assert store2.seen_count() == 0
    assert store2.is_seen(w1, t1) is False
