"""ATH peak tracking on TokenEntry / ScreenedToken."""

from __future__ import annotations

from app.models import ScreenedToken
from app.token_index import TokenEntry, TokenIndex


def test_apply_ath_keeps_peak():
    idx = TokenIndex()
    entry = TokenEntry(
        address="0xAbc",
        dex="uniswap_v3",
        quote_address="0xquote",
        created_block=1,
        ath_mcap=10_000.0,
    )
    row1 = ScreenedToken(address="0xAbc", market_cap=40_000.0, ath_mcap=0.0)
    out1 = idx._apply_ath(entry, row1)
    assert entry.ath_mcap == 40_000.0
    assert out1.ath_mcap == 40_000.0

    row2 = ScreenedToken(address="0xAbc", market_cap=30_000.0, ath_mcap=0.0)
    out2 = idx._apply_ath(entry, row2)
    assert entry.ath_mcap == 40_000.0
    assert out2.ath_mcap == 40_000.0

    row3 = ScreenedToken(address="0xAbc", market_cap=55_000.0, ath_mcap=0.0)
    out3 = idx._apply_ath(entry, row3)
    assert entry.ath_mcap == 55_000.0
    assert out3.ath_mcap == 55_000.0


def test_get_tokens_mirrors_ath():
    idx = TokenIndex()
    entry = TokenEntry(
        address="0xTok",
        dex="uniswap_v3",
        quote_address="0xquote",
        created_block=10,
        ath_mcap=12_000.0,
        screened=ScreenedToken(address="0xTok", market_cap=25_000.0, ath_mcap=0.0),
    )
    idx._tokens[entry.address.lower()] = entry
    rows = idx.get_tokens()
    assert len(rows) == 1
    assert rows[0].ath_mcap == 25_000.0
    assert entry.ath_mcap == 25_000.0
