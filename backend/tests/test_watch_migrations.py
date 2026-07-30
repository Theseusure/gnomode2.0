from pathlib import Path

import pytest

from app.models import BuyerRow, TokenParseResult, WatchConfig, WatchWalletFilters
from app.watch import WatchRunner
from app.watch_store import WatchStore


@pytest.mark.asyncio
async def test_hourly_watch_parses_all_migrations_with_wallet_preset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    store = WatchStore(
        tmp_path / "config.json",
        tmp_path / "seen.json",
        tmp_path / "state.json",
    )
    store.save_config(
        WatchConfig(
            enabled=True,
            # Legacy token limit must not truncate the migration batch.
            max_tokens_per_cycle=1,
            telegram_chat_id="123",
            wallet=WatchWalletFilters(
                mcap_threshold=15_000,
                min_wallet_balance_eth=0.25,
                min_hold_time_minutes=10,
                max_tokens_traded_7d=20,
            ),
        )
    )
    tokens = ["0x" + "1" * 40, "0x" + "2" * 40]
    migration_call = {}

    async def fake_migrations(launchpads, **kwargs):
        migration_call.update({"launchpads": launchpads, **kwargs})
        return ([{"address": token} for token in tokens], {})

    parsed: list[tuple[str, object]] = []

    async def fake_parse(_rpc, token, _threshold, **kwargs):
        parsed.append((token, kwargs["wallet_filters"]))
        return TokenParseResult(
            token=token,
            buyers=[
                BuyerRow(
                    wallet="0x" + token[2],
                    token=token,
                    bought_tokens=1,
                    bought_usd=1,
                    mcap_at_first_buy=1,
                    buys_count=1,
                )
            ],
        )

    sent: list[BuyerRow] = []

    async def fake_send(_chat, buyers, **_kwargs):
        sent.extend(buyers)
        return (["ok"], buyers)

    monkeypatch.setattr("app.watch.telegram_configured", lambda _chat: True)
    monkeypatch.setattr("app.watch.resolve_topic_id", lambda _topic: None)
    monkeypatch.setattr("app.watch.migrated_tokens", fake_migrations)
    monkeypatch.setattr("app.watch.parse_token", fake_parse)
    monkeypatch.setattr("app.watch.send_buyers", fake_send)
    monkeypatch.setattr("app.watch.jobs.has_active", lambda: False)

    status = await WatchRunner(store).run_cycle()

    assert migration_call == {
        "launchpads": {"pons", "flap"},
        "use_dexscreener": True,
        "max_age_hours": 1,
    }
    assert [token for token, _filters in parsed] == tokens
    assert len(sent) == 2
    assert status.last_tokens_screened == 2
    assert status.last_tokens_parsed == 2
    preset = parsed[0][1]
    assert preset.min_wallet_balance_eth == 0.25
    assert preset.min_hold_time_minutes == 10
    assert preset.max_tokens_traded_7d == 20
