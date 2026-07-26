"""Tests for follow-up store and mcap alert gate."""

from __future__ import annotations

from app.followup import should_alert_deal
from app.followup_store import FollowupStore
from app.models import BuyerRow, FollowupConfig


def test_should_alert_deal_low_mcap_only():
    assert should_alert_deal(2, 10_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert should_alert_deal(3, 15_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert not should_alert_deal(2, 50_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert not should_alert_deal(1, 5_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert not should_alert_deal(2, None, max_mcap_alert=15_000, alert_on_deals=[2, 3])


def test_ingest_and_second_deal(tmp_path):
    store = FollowupStore(
        db_path=str(tmp_path / "followup.db"),
        config_path=str(tmp_path / "followup.json"),
    )
    b1 = BuyerRow(
        wallet="0xAAA0000000000000000000000000000000000001",
        token="0xBBB0000000000000000000000000000000000001",
        token_symbol="T1",
        bought_tokens=1.0,
        bought_usd=100.0,
        mcap_at_first_buy=8_000.0,
        buys_count=1,
        first_tx="0xtx1",
    )
    inserted = store.ingest_buyers([b1], max_deals=3, max_mcap_alert=15_000)
    assert len(inserted) == 1
    assert inserted[0].deal_index == 1

    watching = store.list_watching()
    assert len(watching) == 1

    deal2 = store.record_deal(
        wallet=b1.wallet,
        token="0xCCC0000000000000000000000000000000000002",
        token_symbol="T2",
        mcap_at_buy=12_000.0,
        max_deals=3,
    )
    assert deal2 is not None
    assert deal2.deal_index == 2
    assert should_alert_deal(
        deal2.deal_index,
        deal2.mcap_at_buy,
        max_mcap_alert=15_000,
        alert_on_deals=[2, 3],
    )

    # High mcap still recorded, but gate says no alert
    deal3 = store.record_deal(
        wallet=b1.wallet,
        token="0xDDD0000000000000000000000000000000000003",
        token_symbol="T3",
        mcap_at_buy=80_000.0,
        max_deals=3,
    )
    assert deal3 is not None
    assert deal3.deal_index == 3
    assert not should_alert_deal(
        deal3.deal_index,
        deal3.mcap_at_buy,
        max_mcap_alert=15_000,
        alert_on_deals=[2, 3],
    )

    rows = store.list_wallets()
    assert rows[0].status == "done"
    assert rows[0].deal_count == 3


def test_skip_high_mcap_on_ingest(tmp_path):
    store = FollowupStore(
        db_path=str(tmp_path / "followup.db"),
        config_path=str(tmp_path / "followup.json"),
    )
    b = BuyerRow(
        wallet="0xAAA0000000000000000000000000000000000001",
        token="0xBBB0000000000000000000000000000000000001",
        bought_tokens=1.0,
        bought_usd=100.0,
        mcap_at_first_buy=99_000.0,
        buys_count=1,
    )
    inserted = store.ingest_buyers([b], max_mcap_alert=15_000)
    assert inserted == []


def test_config_roundtrip(tmp_path):
    store = FollowupStore(
        db_path=str(tmp_path / "followup.db"),
        config_path=str(tmp_path / "followup.json"),
    )
    cfg = FollowupConfig(enabled=True, max_mcap_alert=12_000, raybot_enabled=True)
    store.save_config(cfg)
    loaded = store.load_config()
    assert loaded.enabled is True
    assert loaded.max_mcap_alert == 12_000
    assert loaded.raybot_enabled is True


def test_raybot_low_mcap_settings():
    from app.raybot import RayBotClient

    s = RayBotClient.low_mcap_evm_settings(15_000)
    assert s["evm_buys"] is True
    assert s["evm_sells"] is False
    assert s["evm_mc_trade_max"] == 15_000.0
