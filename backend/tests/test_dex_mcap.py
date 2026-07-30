"""DexScreener market-cap: prefer priceUsd × supply."""

from app.screener import _dex_market_cap, _pair_to_screened


def test_mcap_from_price_usd_times_1e9() -> None:
    pair = {
        "baseToken": {"address": "0xTok", "symbol": "TOK", "name": "Tok"},
        "quoteToken": {
            "address": "0x0000000000000000000000000000000000000000",
            "symbol": "ETH",
        },
        "priceUsd": 0.00006456,
        "priceNative": 0.00000003276,
        "marketCap": 44774,  # stale DS — ignored when priceUsd present
        "fdv": 44774,
        "liquidity": {"usd": 32_000},
        "txns": {"h24": {"buys": 1, "sells": 1}},
        "pairAddress": "0xpair",
        "dexId": "uniswap",
        "chainId": "robinhood",
    }
    assert abs(_dex_market_cap(pair) - 64_560.0) < 1.0
    row = _pair_to_screened("0xTok", {}, pair)
    assert abs(row.market_cap - 64_560.0) < 1.0


def test_mcap_fallback_to_ds_when_no_price() -> None:
    pair = {
        "baseToken": {"address": "0xTok", "symbol": "TOK", "name": "Tok"},
        "quoteToken": {"address": "0xquote", "symbol": "WETH"},
        "marketCap": 12_345,
        "fdv": 12_345,
        "liquidity": {"usd": 1_000},
        "txns": {"h24": {"buys": 1, "sells": 1}},
        "pairAddress": "0xpair",
        "dexId": "uniswap",
        "chainId": "robinhood",
    }
    assert abs(_dex_market_cap(pair) - 12_345.0) < 1.0


def test_custom_supply() -> None:
    pair = {"priceUsd": 2.0, "marketCap": 1}
    assert _dex_market_cap(pair, supply=100.0) == 200.0
