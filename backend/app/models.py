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


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: JobProgress
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
    min_traders: float | None = None
    max_traders: float | None = None
    min_pair_age_hours: float | None = None
    max_pair_age_hours: float | None = None
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
    traders_24h: int = 0
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
