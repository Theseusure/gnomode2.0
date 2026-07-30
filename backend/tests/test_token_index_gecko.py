"""Gecko ATH bumps entry.ath_mcap in the token index."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ath_gecko import GeckoAthResult
from app.models import ScreenedToken
from app.token_index import TokenEntry, TokenIndex


@pytest.mark.asyncio
async def test_apply_gecko_peaks_bumps_ath():
    idx = TokenIndex()
    entry = TokenEntry(
        address="0xTok",
        dex="uniswap_v3",
        quote_address="0xquote",
        created_block=10,
        pool_address="0xpool",
        ath_mcap=10_000.0,
        screened=ScreenedToken(
            address="0xTok",
            symbol="TOK",
            market_cap=10_000.0,
            ath_mcap=10_000.0,
        ),
    )
    idx._tokens["0xtok"] = entry

    fake = GeckoAthResult(token="0xtok", ath_mcap=77_000.0, pool="0xpool")
    with patch(
        "app.ath_gecko.fetch_token_ath_mcap",
        new=AsyncMock(return_value=fake),
    ):
        n = await idx._apply_gecko_peaks(["0xTok"], limit=10)

    assert n == 1
    assert entry.ath_mcap == 77_000.0
    assert entry.gecko_ath_at > 0
    assert entry.screened is not None
    assert entry.screened.ath_mcap == 77_000.0
