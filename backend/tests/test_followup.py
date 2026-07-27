"""Tests for follow-up store and mcap alert gate."""

from __future__ import annotations

import pytest

from app.followup import should_alert_deal
from app.followup_store import FollowupStore
from app.models import BuyerRow, FollowupConfig


def test_should_alert_deal_low_mcap_only():
    assert should_alert_deal(2, 10_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert should_alert_deal(3, 15_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert not should_alert_deal(2, 50_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert not should_alert_deal(1, 5_000, max_mcap_alert=15_000, alert_on_deals=[2, 3])
    assert not should_alert_deal(2, None, max_mcap_alert=15_000, alert_on_deals=[2, 3])


def test_should_alert_min_mcap_and_usd():
    assert not should_alert_deal(
        2,
        500,
        max_mcap_alert=15_000,
        alert_on_deals=[2, 3],
        min_mcap_alert=1_000,
    )
    assert should_alert_deal(
        2,
        2_000,
        max_mcap_alert=15_000,
        alert_on_deals=[2, 3],
        min_mcap_alert=1_000,
    )
    assert not should_alert_deal(
        2,
        5_000,
        max_mcap_alert=15_000,
        alert_on_deals=[2, 3],
        bought_usd=5,
        min_bought_usd=50,
    )
    assert should_alert_deal(
        2,
        5_000,
        max_mcap_alert=15_000,
        alert_on_deals=[2, 3],
        bought_usd=100,
        min_bought_usd=50,
        max_bought_usd=500,
    )


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


def test_should_alert_requires_bought_usd_when_min_set():
    assert not should_alert_deal(
        2,
        5_000,
        max_mcap_alert=15_000,
        alert_on_deals=[2, 3],
        bought_usd=None,
        min_bought_usd=50,
    )


def test_estimate_bought_usd_from_transfer():
    from app.followup import estimate_bought_usd, _transfer_token_amount

    item = {
        "total": {"value": "1000000000000000000", "decimals": "18"},
        "token": {"decimals": "18"},
    }
    assert _transfer_token_amount(item) == pytest.approx(1.0)
    assert estimate_bought_usd(item, 2.5) == pytest.approx(2.5)
    assert estimate_bought_usd(item, None) is None


def test_is_buy_like_transfer_gates():
    from app.followup import _is_buy_like_transfer

    wallet = "0xaaa0000000000000000000000000000000000001"
    dex_in = {
        "to": {"hash": wallet},
        "from": {"hash": "0xdex", "is_contract": True},
    }
    eoa_in = {
        "to": {"hash": wallet},
        "from": {"hash": "0xeoa", "is_contract": False},
    }
    out_tx = {
        "to": {"hash": "0xother"},
        "from": {"hash": wallet, "is_contract": False},
    }
    assert _is_buy_like_transfer(dex_in, wallet, buys_only=True, track_transfers=False)
    assert not _is_buy_like_transfer(eoa_in, wallet, buys_only=True, track_transfers=False)
    assert not _is_buy_like_transfer(eoa_in, wallet, buys_only=False, track_transfers=False)
    assert _is_buy_like_transfer(eoa_in, wallet, buys_only=False, track_transfers=True)
    assert not _is_buy_like_transfer(out_tx, wallet, buys_only=True, track_transfers=True)


def test_config_track_transfers_default(tmp_path):
    store = FollowupStore(
        db_path=str(tmp_path / "followup.db"),
        config_path=str(tmp_path / "followup.json"),
    )
    cfg = store.load_config()
    assert cfg.buys_only is True
    assert cfg.track_transfers is False
    cfg = cfg.model_copy(update={"track_transfers": True, "buys_only": False})
    store.save_config(cfg)
    loaded = store.load_config()
    assert loaded.track_transfers is True
    assert loaded.buys_only is False


def test_record_deal_stores_bought_usd(tmp_path):
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
        wallet_balance_eth=1.5,
        tokens_traded_7d=4,
    )
    store.ingest_buyers([b1], max_deals=3, max_mcap_alert=15_000)
    deal2 = store.record_deal(
        wallet=b1.wallet,
        token="0xCCC0000000000000000000000000000000000002",
        token_symbol="T2",
        mcap_at_buy=9_000.0,
        bought_usd=250.0,
        max_deals=3,
    )
    assert deal2 is not None
    assert deal2.bought_usd == 250.0
    rows = store.list_wallets(include_deals=True)
    assert rows[0].wallet_balance_eth == 1.5
    assert rows[0].tokens_traded_7d == 4
    assert any(d.bought_usd == 250.0 for d in rows[0].deals)
