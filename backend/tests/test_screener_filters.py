"""Screener primary filters including min ATH mcap."""

from app.models import ScreenedToken, ScreenRequest
from app.screener import _passes_primary


def _row(**kwargs) -> ScreenedToken:
    base = dict(
        address="0x" + "ab" * 20,
        symbol="T",
        liquidity_usd=10_000.0,
        market_cap=20_000.0,
        ath_mcap=0.0,
        traders_24h=200,
    )
    base.update(kwargs)
    return ScreenedToken(**base)


def test_min_ath_mcap_filters_peak() -> None:
    req = ScreenRequest(min_ath_mcap=40_000.0)
    assert not _passes_primary(_row(ath_mcap=12_000.0, market_cap=12_000.0), req)
    assert _passes_primary(_row(ath_mcap=55_000.0, market_cap=10_000.0), req)


def test_min_ath_mcap_off_when_none_or_zero() -> None:
    row = _row(ath_mcap=0.0, market_cap=5_000.0)
    assert _passes_primary(row, ScreenRequest())
    assert _passes_primary(row, ScreenRequest(min_ath_mcap=None))
    assert _passes_primary(row, ScreenRequest(min_ath_mcap=0.0))
