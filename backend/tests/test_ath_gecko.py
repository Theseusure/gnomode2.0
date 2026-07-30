"""GeckoTerminal OHLCV → peak mcap."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ath_gecko import fetch_ohlcv_peak_price, fetch_token_ath_mcap


@pytest.mark.asyncio
async def test_ohlcv_peak_price_from_highs():
    payload = {
        "data": {
            "attributes": {
                "ohlcv_list": [
                    [100, 1.0, 3.0, 0.5, 2.0, 10],
                    [90, 0.8, 2.5, 0.4, 1.0, 5],
                ]
            }
        }
    }

    class Resp:
        status_code = 200

        def json(self):
            return payload

    client = AsyncMock()
    client.get = AsyncMock(return_value=Resp())
    with patch("app.ath_gecko.http_client", return_value=client):
        peak, n = await fetch_ohlcv_peak_price("0xpool")
    assert peak == 3.0
    assert n == 2


@pytest.mark.asyncio
async def test_token_ath_mcap_uses_supply():
    with (
        patch("app.ath_gecko.resolve_pool_address", new=AsyncMock(return_value="0xpool")),
        patch("app.ath_gecko.resolve_supply", new=AsyncMock(return_value=1_000_000_000.0)),
        patch("app.ath_gecko.fetch_ohlcv_peak_price", new=AsyncMock(return_value=(0.00005, 10))),
        patch.dict("app.ath_gecko._CACHE", {}, clear=True),
    ):
        res = await fetch_token_ath_mcap("0xTok", use_cache=False)
    assert abs(res.ath_mcap - 50_000.0) < 1.0
    assert res.pool == "0xpool"
    assert res.candles == 10
