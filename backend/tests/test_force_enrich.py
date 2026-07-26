"""force_enrich_addresses updates index ATH and returns orphan rows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models import ScreenedToken
from app.token_index import TokenEntry, TokenIndex


@pytest.mark.asyncio
async def test_force_enrich_updates_index_entry():
    idx = TokenIndex()
    entry = TokenEntry(
        address="0xTok",
        dex="uniswap_v3",
        quote_address="0xquote",
        created_block=10,
        ath_mcap=10_000.0,
        screened=ScreenedToken(address="0xTok", market_cap=10_000.0, ath_mcap=10_000.0),
        enriched_at=0.0,
    )
    idx._tokens["0xtok"] = entry

    pair = {
        "chainId": "robinhood",
        "baseToken": {"address": "0xTok", "symbol": "TOK", "name": "Tok"},
        "quoteToken": {"address": "0xquote", "symbol": "WETH"},
        "liquidity": {"usd": 50_000},
        "marketCap": 60_000,
        "fdv": 60_000,
        "txns": {"h24": {"buys": 10, "sells": 5}},
        "pairCreatedAt": 1,
        "url": "https://example.com",
        "dexId": "uniswap",
    }

    with patch(
        "app.screener._fetch_dex_pairs",
        new=AsyncMock(return_value=[pair]),
    ):
        out = await idx.force_enrich_addresses(["0xTok"])

    assert "0xtok" in out
    assert entry.ath_mcap == 60_000.0
    assert out["0xtok"].ath_mcap == 60_000.0


@pytest.mark.asyncio
async def test_force_enrich_orphan_not_added_to_index():
    idx = TokenIndex()
    pair = {
        "chainId": "robinhood",
        "baseToken": {"address": "0xOrphan", "symbol": "ORP", "name": "Orp"},
        "quoteToken": {"address": "0xquote", "symbol": "WETH"},
        "liquidity": {"usd": 1_000},
        "marketCap": 55_000,
        "fdv": 55_000,
        "txns": {"h24": {"buys": 1, "sells": 1}},
        "pairCreatedAt": 1,
        "url": "https://example.com",
        "dexId": "uniswap",
    }

    with patch(
        "app.screener._fetch_dex_pairs",
        new=AsyncMock(return_value=[pair]),
    ):
        out = await idx.force_enrich_addresses(["0xOrphan"])

    assert "0xorphan" in out
    assert out["0xorphan"].market_cap == 55_000.0
    assert out["0xorphan"].ath_mcap == 55_000.0
    assert "0xorphan" not in idx._tokens
