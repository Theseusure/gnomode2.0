"""token_index.mcap_peaks helper for ATH peaks."""

from __future__ import annotations

from app.models import ScreenedToken
from app.token_index import TokenEntry, TokenIndex


def test_mcap_peaks_uses_entry_and_row_ath():
    idx = TokenIndex()
    entry = TokenEntry(
        address="0xAbc",
        dex="uniswap_v4",
        quote_address="0xquote",
        created_block=1,
        ath_mcap=40_000.0,
        screened=ScreenedToken(
            address="0xAbc",
            symbol="ABC",
            market_cap=55_000.0,
            ath_mcap=42_000.0,
        ),
    )
    idx._tokens[entry.address.lower()] = entry
    peaks = idx.mcap_peaks(["0xAbC", "0xmissing"])
    assert "0xabc" in peaks
    assert "0xmissing" not in peaks
    ath, sym = peaks["0xabc"]
    assert ath == 55_000.0
    assert sym == "ABC"
    assert entry.ath_mcap == 55_000.0
