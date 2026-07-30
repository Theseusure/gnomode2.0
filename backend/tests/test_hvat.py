"""Хвать profile unit tests."""

from __future__ import annotations

from pathlib import Path

from app.followup_store import FollowupStore
from app.hvat import HVAT_MCAP, apply_hvat_profile
from app.watch_store import WatchStore


def test_apply_hvat_profile(tmp_path: Path, monkeypatch):
    wstore = WatchStore(
        config_path=tmp_path / "watch.json",
        seen_path=tmp_path / "seen.json",
        state_path=tmp_path / "state.json",
    )
    fstore = FollowupStore(
        db_path=str(tmp_path / "followup.db"),
        config_path=str(tmp_path / "followup.json"),
    )

    import app.hvat as hvat_mod
    import app.watch as watch_mod
    import app.followup as follow_mod

    monkeypatch.setattr(hvat_mod, "watch_store", wstore)
    monkeypatch.setattr(hvat_mod, "followup_store", fstore)
    monkeypatch.setattr(watch_mod, "watch_store", wstore)
    monkeypatch.setattr(follow_mod, "followup_store", fstore)
    # Avoid waking real runners
    monkeypatch.setattr(hvat_mod.watch_runner, "notify_config_changed", lambda: None)
    monkeypatch.setattr(hvat_mod.followup_runner, "notify_config_changed", lambda: None)

    out = apply_hvat_profile(enable=True)
    assert out["ok"] is True
    assert out["mcap_cap"] == HVAT_MCAP

    w = wstore.load_config()
    assert w.enabled is True
    assert w.wallet.mcap_threshold == HVAT_MCAP
    assert w.wallet.min_tokens_traded_7d == 1
    assert w.wallet.max_tokens_traded_7d == 1

    f = fstore.load_config()
    assert f.enabled is True
    assert f.max_mcap_alert == HVAT_MCAP
    assert f.ingest_from_watch is True
    assert f.alert_on_deals == [2, 3]
