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
        hold_path=tmp_path / "hold.json",
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
    monkeypatch.setattr(hvat_mod.watch_runner, "notify_config_changed", lambda: None)
    monkeypatch.setattr(hvat_mod.followup_runner, "notify_config_changed", lambda: None)

    out = apply_hvat_profile(enable=True)
    assert out["ok"] is True

    w = wstore.load_config()
    assert w.enabled is True
    assert w.wallet.mcap_threshold == HVAT_MCAP
    assert w.wallet.min_tokens_traded_7d == 1
    assert w.wallet.max_tokens_traded_7d == 1
    assert w.wallet.tokens_unique_period.value == "7d"

    f = fstore.load_config()
    assert f.enabled is True
    assert f.max_mcap_alert == HVAT_MCAP
    assert f.ingest_from_watch is True
    assert f.alert_on_deals == [2, 3]


def test_save_hvat_filters_period(tmp_path: Path, monkeypatch):
    from app.hvat import save_hvat_filters
    from app.models import TokensUniquePeriod

    wstore = WatchStore(
        config_path=tmp_path / "watch.json",
        seen_path=tmp_path / "seen.json",
        state_path=tmp_path / "state.json",
        hold_path=tmp_path / "hold.json",
    )
    fstore = FollowupStore(
        db_path=str(tmp_path / "followup.db"),
        config_path=str(tmp_path / "followup.json"),
    )
    import app.hvat as hvat_mod

    monkeypatch.setattr(hvat_mod, "watch_store", wstore)
    monkeypatch.setattr(hvat_mod, "followup_store", fstore)
    monkeypatch.setattr(hvat_mod.watch_runner, "notify_config_changed", lambda: None)
    monkeypatch.setattr(hvat_mod.followup_runner, "notify_config_changed", lambda: None)

    out = save_hvat_filters(
        screen={"min_liq": 1000, "min_ath_mcap": 40_000, "max_results": 100},
        wallet={
            "mcap_threshold": 18_000,
            "min_tokens_traded_7d": 1,
            "max_tokens_traded_7d": 1,
            "tokens_unique_period": "3d",
            "min_wallet_balance_eth": 0.01,
        },
        max_tokens_per_cycle=15,
    )
    assert out["ok"] is True
    w = wstore.load_config()
    assert w.screen.min_liq == 1000
    assert w.screen.min_ath_mcap == 40_000
    assert w.max_tokens_per_cycle == 15
    assert w.wallet.tokens_unique_period == TokensUniquePeriod.d3
    assert w.wallet.min_wallet_balance_eth == 0.01
    assert fstore.load_config().max_mcap_alert == 18_000


def test_tokens_unique_period_hours():
    from app.models import tokens_unique_period_hours

    assert tokens_unique_period_hours("12h") == 12
    assert tokens_unique_period_hours("24h") == 24
    assert tokens_unique_period_hours("1d") == 24
    assert tokens_unique_period_hours("30d") == 720
