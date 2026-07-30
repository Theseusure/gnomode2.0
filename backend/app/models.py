"""Pydantic models for API and parser results."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class ParseRequest(BaseModel):
    tokens: list[str] = Field(..., min_length=1)
    mcap_threshold: float | None = None
    exclude_honeypots: bool = True
    # Wallet filters (all optional min/max ranges, applied to found buyers)
    min_wallet_balance_eth: float | None = None
    max_wallet_balance_eth: float | None = None
    min_hold_time_minutes: float | None = None
    max_hold_time_minutes: float | None = None
    min_tokens_traded_7d: float | None = None
    max_tokens_traded_7d: float | None = None


class MigratedToken(BaseModel):
    launchpad: str
    address: str
    name: str | None = None
    symbol: str | None = None
    image_url: str | None = None
    migrated_at: str | None = None
    pool_address: str | None = None
    source_url: str
    verification: str
    discovery_sources: list[str] = Field(default_factory=list)
    liquidity_usd: float = 0
    traders_24h: int = 0


class MigrationResponse(BaseModel):
    tokens: list[MigratedToken] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    count: int = 0
    duration_ms: int = 0


class BuyerRow(BaseModel):
    wallet: str
    token: str
    token_symbol: str = ""
    bought_tokens: float
    bought_usd: float
    mcap_at_first_buy: float
    buys_count: int
    first_tx: str = ""
    first_block: int = 0
    wallet_balance_eth: float | None = None
    hold_time_minutes: float | None = None
    tokens_traded_7d: int | None = None


class PoolInfo(BaseModel):
    address: str  # pair/pool contract, or PoolManager for V4
    dex: str  # uniswap_v2 | uniswap_v3 | uniswap_v4
    quote: str
    quote_symbol: str
    token0: str
    token1: str
    fee: int | None = None
    liquidity_usd: float = 0.0
    created_block: int | None = None
    pool_id: str | None = None  # bytes32 for Uniswap V4
    pair_created_at_ms: int | None = None


class TokenParseResult(BaseModel):
    token: str
    symbol: str = ""
    name: str = ""
    decimals: int = 18
    total_supply: float = 0.0
    pool: PoolInfo | None = None
    buyers: list[BuyerRow] = Field(default_factory=list)
    error: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)


class JobProgress(BaseModel):
    stage: str = "queued"
    message: str = ""
    percent: float = 0.0
    current_token: str | None = None


class JobLogEntry(BaseModel):
    """One step in the parse/filter pipeline (shown in the UI log)."""

    ts: float
    stage: str
    message: str
    percent: float = 0.0
    token: str | None = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: JobProgress
    log: list[JobLogEntry] = Field(default_factory=list)
    results: list[TokenParseResult] = Field(default_factory=list)
    error: str | None = None


class ScreenSortBy(str, Enum):
    liquidity = "liquidity"
    market_cap = "market_cap"
    traders = "traders"
    pair_age = "pair_age"


class ScreenSortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class ScreenRequest(BaseModel):
    min_liq: float | None = None
    max_liq: float | None = None
    min_mcap: float | None = None
    max_mcap: float | None = None
    # Peak/ATH mcap from the 24h index (Gecko OHLCV + DS samples). None/0 = off.
    min_ath_mcap: float | None = None
    min_traders: float | None = None
    max_traders: float | None = None
    min_pair_age_hours: float | None = None
    max_pair_age_hours: float | None = None
    exclude_honeypots: bool = True
    sort_by: ScreenSortBy = ScreenSortBy.liquidity
    sort_order: ScreenSortOrder = ScreenSortOrder.desc
    max_results: int = Field(default=500, ge=1, le=2000)


class ScreenedToken(BaseModel):
    address: str
    symbol: str = ""
    name: str = ""
    pair_address: str = ""
    dex_id: str = ""
    price_usd: float = 0.0
    liquidity_usd: float = 0.0
    market_cap: float = 0.0
    # Peak market cap observed while the token is in the 24h index.
    ath_mcap: float = 0.0
    traders_24h: int = 0
    buys_24h: int = 0
    sells_24h: int = 0
    pair_created_at_ms: int | None = None
    pair_age_hours: float | None = None
    url: str = ""
    gmgn_url: str = ""


class ScreenJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: JobProgress
    results: list[ScreenedToken] = Field(default_factory=list)
    error: str | None = None


class IndexStatus(BaseModel):
    tokens_24h: int = 0
    enriched: int = 0
    building: bool = False
    cold_started: bool = False
    refreshing: bool = False
    last_tip: int = 0
    last_scan_ts: float = 0.0
    last_refresh_ts: float = 0.0
    window_hours: int = 24


class WatchScreenFilters(BaseModel):
    min_liq: float | None = None
    max_liq: float | None = None
    min_mcap: float | None = None
    max_mcap: float | None = None
    # Same as ScreenRequest: require indexed ATH ≥ threshold (Gecko + DS).
    min_ath_mcap: float | None = None
    min_traders: float | None = None
    max_traders: float | None = None
    min_pair_age_hours: float | None = None
    max_pair_age_hours: float | None = None
    exclude_honeypots: bool = True
    sort_by: ScreenSortBy = ScreenSortBy.liquidity
    sort_order: ScreenSortOrder = ScreenSortOrder.desc
    max_results: int = Field(default=500, ge=1, le=2000)


class WatchWalletFilters(BaseModel):
    mcap_threshold: float | None = None
    exclude_honeypots: bool = True
    min_wallet_balance_eth: float | None = None
    max_wallet_balance_eth: float | None = None
    min_hold_time_minutes: float | None = None
    max_hold_time_minutes: float | None = None
    min_tokens_traded_7d: float | None = None
    max_tokens_traded_7d: float | None = None


class WatchConfig(BaseModel):
    enabled: bool = False
    interval_sec: int = Field(default=900, ge=60, le=86400)
    max_tokens_per_cycle: int = Field(default=20, ge=1, le=2000)
    telegram_chat_id: str = ""
    # Forum topic id (Telegram message_thread_id). Empty → no topic / General.
    telegram_topic_id: str = ""
    # Periodic tired-gnome status lines in Telegram (every ~10–15 min).
    gnome_banter_enabled: bool = True
    screen: WatchScreenFilters = Field(default_factory=WatchScreenFilters)
    wallet: WatchWalletFilters = Field(default_factory=WatchWalletFilters)


class WatchStatus(BaseModel):
    enabled: bool = False
    running: bool = False
    telegram_configured: bool = False
    next_run_ts: float | None = None
    last_run_ts: float | None = None
    last_run_duration_sec: float | None = None
    last_error: str | None = None
    last_message: str = ""
    last_tokens_screened: int = 0
    last_tokens_parsed: int = 0
    last_buyers_found: int = 0
    last_buyers_new: int = 0
    last_buyers_sent: int = 0
    last_buyers_skipped: int = 0
    seen_count: int = 0
    # Catch-up after downtime (before regular interval cycles)
    needs_catchup: bool = False
    catchup_lookback_hours: float | None = None
    is_catchup_run: bool = False
    gnome_banter_enabled: bool = True
    gnome_banter_next_ts: float | None = None
    stop_requested: bool = False
    log: list[JobLogEntry] = Field(default_factory=list)
