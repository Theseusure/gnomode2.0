"""Robinhood token screener: Blockscout catalog + DexScreener metrics."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .blockscout import blockscout_api_base, blockscout_headers
from .constants import DEXSCREENER_API, QUOTE_TOKENS, ZERO
from .models import ScreenedToken, ScreenRequest, ScreenSortBy, ScreenSortOrder
from .security import assess_tokens_honeypot

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, str, float], Awaitable[None]]
TokensCb = Callable[[list[ScreenedToken]], Awaitable[None]]

_BATCH = 30
_DEX_CONCURRENCY = 6
_BS_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
_DS_TIMEOUT = httpx.Timeout(12.0, connect=8.0)

_KNOWN_QUOTES = {a.lower() for a in QUOTE_TOKENS} | {ZERO.lower()}


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _in_range(value: float | None, lo: float | None, hi: float | None) -> bool:
    if lo is None and hi is None:
        return True
    if value is None:
        return False
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


async def _fetch_blockscout_page(
    client: httpx.AsyncClient, params: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    url = f"{blockscout_api_base()}/tokens"
    query: dict[str, Any] = {"type": "ERC-20"}
    if params:
        for k, v in params.items():
            if isinstance(v, bool):
                query[k] = "true" if v else "false"
            else:
                query[k] = v

    delay = 0.3
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            resp = await client.get(
                url,
                params=query,
                headers=blockscout_headers(),
                timeout=_BS_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items") if isinstance(data, dict) else None
                if not isinstance(items, list):
                    items = []
                next_params = data.get("next_page_params") if isinstance(data, dict) else None
                return items, next_params if isinstance(next_params, dict) else None
            if resp.status_code in (429, 500, 502, 503):
                logger.warning("Blockscout tokens %s (try %s)", resp.status_code, attempt + 1)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 3.0)
                continue
            logger.warning("Blockscout tokens %s: %s", resp.status_code, resp.text[:200])
            return [], None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("Blockscout tokens page error (try %s): %r", attempt + 1, exc)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 3.0)
    logger.warning("Blockscout tokens gave up: %r", last_exc)
    return [], None


async def _fetch_dex_pairs(
    client: httpx.AsyncClient, addresses: list[str]
) -> list[dict[str, Any]]:
    url = f"{DEXSCREENER_API}/tokens/v1/robinhood/{','.join(addresses)}"
    delay = 0.2
    for attempt in range(4):
        try:
            resp = await client.get(url, timeout=_DS_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    pairs = data.get("pairs")
                    return pairs if isinstance(pairs, list) else []
                return []
            if resp.status_code in (429, 502, 503):
                await asyncio.sleep(delay)
                delay = min(delay * 2.5, 3.0)
                continue
            logger.warning("DexScreener tokens/v1 %s: %s", resp.status_code, resp.text[:200])
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("DexScreener enrich error (try %s): %r", attempt + 1, exc)
            await asyncio.sleep(delay)
            delay = min(delay * 2.5, 3.0)
    return []


def _best_pair_for_token(token: str, pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    t = token.lower()
    best: dict[str, Any] | None = None
    best_liq = -1.0
    for p in pairs:
        chain = str(p.get("chainId") or "").lower()
        if chain and chain not in ("robinhood", "4663"):
            continue
        base = str((p.get("baseToken") or {}).get("address") or "").lower()
        quote = str((p.get("quoteToken") or {}).get("address") or "").lower()
        if t not in (base, quote):
            continue
        liq = _f((p.get("liquidity") or {}).get("usd"))
        # Prefer RH pairs; score ties by liquidity
        score = liq if chain in ("robinhood", "4663") else liq - 1_000_000_000_000.0
        if score > best_liq:
            best_liq = score
            best = p
    return best


def _pair_to_screened(
    token_addr: str, meta: dict[str, Any], pair: dict[str, Any]
) -> ScreenedToken:
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    t = token_addr.lower()
    if str(base.get("address") or "").lower() == t:
        symbol = str(base.get("symbol") or meta.get("symbol") or "")
        name = str(base.get("name") or meta.get("name") or "")
    else:
        symbol = str(quote.get("symbol") or meta.get("symbol") or "")
        name = str(quote.get("name") or meta.get("name") or "")

    created = pair.get("pairCreatedAt")
    created_ms = int(created) if created is not None else None
    age_h: float | None = None
    if created_ms is not None and created_ms > 0:
        age_h = max(0.0, (time.time() * 1000 - created_ms) / 3_600_000)

    pair_addr = str(pair.get("pairAddress") or "")
    chain = str(pair.get("chainId") or "robinhood")
    ds_url = str(pair.get("url") or f"https://dexscreener.com/{chain}/{pair_addr}")

    txns = (pair.get("txns") or {}).get("h24") or {}
    buys = int(_f(txns.get("buys")))
    sells = int(_f(txns.get("sells")))
    traders = buys + sells

    mcap = pair.get("marketCap")
    if mcap is None:
        mcap = pair.get("fdv")

    return ScreenedToken(
        address=token_addr,
        symbol=symbol,
        name=name,
        pair_address=pair_addr,
        dex_id=str(pair.get("dexId") or ""),
        price_usd=_f(pair.get("priceUsd")),
        liquidity_usd=_f((pair.get("liquidity") or {}).get("usd")),
        market_cap=_f(mcap),
        traders_24h=traders,
        buys_24h=buys,
        sells_24h=sells,
        pair_created_at_ms=created_ms,
        pair_age_hours=age_h,
        url=ds_url,
        gmgn_url=f"https://gmgn.ai/robinhood/token/{token_addr}",
    )


def _passes_primary(row: ScreenedToken, req: ScreenRequest) -> bool:
    if not _in_range(row.liquidity_usd, req.min_liq, req.max_liq):
        return False
    if not _in_range(row.market_cap, req.min_mcap, req.max_mcap):
        return False
    if not _in_range(float(row.traders_24h), req.min_traders, req.max_traders):
        return False
    if req.min_pair_age_hours is not None or req.max_pair_age_hours is not None:
        if row.pair_age_hours is None:
            return False
        if not _in_range(row.pair_age_hours, req.min_pair_age_hours, req.max_pair_age_hours):
            return False
    return True


def _sort_key(row: ScreenedToken, sort_by: ScreenSortBy) -> float:
    if sort_by == ScreenSortBy.market_cap:
        return row.market_cap
    if sort_by == ScreenSortBy.traders:
        return float(row.traders_24h)
    if sort_by == ScreenSortBy.pair_age:
        return row.pair_age_hours if row.pair_age_hours is not None else -1.0
    return row.liquidity_usd


def _sorted_rows(rows: list[ScreenedToken], req: ScreenRequest) -> list[ScreenedToken]:
    reverse = req.sort_order == ScreenSortOrder.desc
    out = sorted(rows, key=lambda r: _sort_key(r, req.sort_by), reverse=reverse)
    return out[: req.max_results]


def _page_candidates(
    items: list[Any],
    seen_addr: set[str],
    matched: dict[str, ScreenedToken],
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        addr = str(item.get("address_hash") or item.get("address") or "").strip()
        if not addr.startswith("0x"):
            continue
        key = addr.lower()
        if key in _KNOWN_QUOTES or key in seen_addr or key in matched:
            continue
        seen_addr.add(key)
        out.append((addr, item))
    return out


async def _enrich_candidates(
    client: httpx.AsyncClient,
    candidates: list[tuple[str, dict[str, Any]]],
    req: ScreenRequest,
) -> list[ScreenedToken]:
    if not candidates:
        return []

    batches = [candidates[i : i + _BATCH] for i in range(0, len(candidates), _BATCH)]
    sem = asyncio.Semaphore(_DEX_CONCURRENCY)

    async def run_batch(batch: list[tuple[str, dict[str, Any]]]) -> list[ScreenedToken]:
        addrs = [a for a, _ in batch]
        meta_by = {a.lower(): m for a, m in batch}
        async with sem:
            pairs = await _fetch_dex_pairs(client, addrs)

        by_token: dict[str, list[dict[str, Any]]] = {a.lower(): [] for a in addrs}
        for p in pairs:
            for side in ("baseToken", "quoteToken"):
                addr = str((p.get(side) or {}).get("address") or "").lower()
                if addr in by_token:
                    by_token[addr].append(p)

        out: list[ScreenedToken] = []
        for addr, _ in batch:
            key = addr.lower()
            best = _best_pair_for_token(addr, by_token.get(key, []))
            if not best:
                continue
            row = _pair_to_screened(addr, meta_by.get(key, {}), best)
            if _passes_primary(row, req):
                out.append(row)
        return out

    parts = await asyncio.gather(*(run_batch(b) for b in batches))
    merged: list[ScreenedToken] = []
    for part in parts:
        merged.extend(part)
    return merged


async def _filter_honeypots(rows: list[ScreenedToken]) -> list[ScreenedToken]:
    """Filter honeypots via GMGN security (not inside page timeouts)."""
    if not rows:
        return []
    verdicts = await assess_tokens_honeypot(
        [(r.address, r.buys_24h, r.sells_24h) for r in rows]
    )
    kept: list[ScreenedToken] = []
    for row in rows:
        reason = verdicts.get(row.address.lower())
        if reason:
            logger.info(
                "Screener skip honeypot %s (%s): %s",
                row.symbol or row.address[:10],
                row.address[:12],
                reason,
            )
            continue
        kept.append(row)
    return kept


async def screen_tokens(
    req: ScreenRequest,
    on_progress: ProgressCb | None = None,
    on_tokens: TokensCb | None = None,
) -> list[ScreenedToken]:
    async def prog(stage: str, message: str, percent: float) -> None:
        if on_progress:
            await on_progress(stage, message, percent)

    async def emit(rows: list[ScreenedToken]) -> None:
        if on_tokens:
            await on_tokens(_sorted_rows(rows, req))

    await prog("catalog", "Fetching token catalog…", 0.02)

    matched: dict[str, ScreenedToken] = {}
    seen_addr: set[str] = set()
    page = 0
    next_params: dict[str, Any] | None = None
    max_pages = min(40, max(8, req.max_results // 10 + 6))
    # Stop as soon as we have enough matches. When excluding honeypots we
    # over-fetch only a small buffer (honeypots are a minority) so the final
    # list still fills max_results — never scan the whole catalog needlessly.
    stop_target = req.max_results
    if req.exclude_honeypots:
        stop_target = min(int(req.max_results * 1.4) + 10, req.max_results + 200)
    consecutive_empty = 0

    async with httpx.AsyncClient(
        timeout=_BS_TIMEOUT,
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        headers={"User-Agent": "gnomode/1.0", "Accept": "application/json"},
        follow_redirects=True,
    ) as client:
        while page < max_pages:
            page += 1
            await prog(
                "catalog",
                f"Loading catalog page {page}/{max_pages}…",
                min(0.2, 0.02 + page * 0.01),
            )

            try:
                items, next_params = await asyncio.wait_for(
                    _fetch_blockscout_page(client, next_params),
                    timeout=18.0,
                )
            except TimeoutError:
                logger.warning("Blockscout page %s timed out", page)
                consecutive_empty += 1
                if consecutive_empty >= 3 or not next_params:
                    break
                continue

            if not items:
                consecutive_empty += 1
                if consecutive_empty >= 3 or not next_params:
                    break
                continue

            page_cands = _page_candidates(items, seen_addr, matched)
            if not page_cands:
                consecutive_empty += 1
                if consecutive_empty >= 3 or not next_params:
                    break
                if not next_params:
                    break
                continue

            consecutive_empty = 0
            await prog(
                "enrich",
                f"Page {page} — enriching {len(page_cands)} tokens",
                min(0.75, 0.15 + page * 0.55 / max_pages),
            )

            try:
                rows = await asyncio.wait_for(
                    _enrich_candidates(client, page_cands, req),
                    timeout=45.0,
                )
            except TimeoutError:
                logger.warning("Dex enrich page %s timed out", page)
                rows = []

            for row in rows:
                matched[row.address.lower()] = row

            await prog(
                "enrich",
                f"Page {page} — {len(matched)} match filters ({len(seen_addr)} scanned)",
                min(0.8, 0.2 + page * 0.55 / max_pages),
            )
            await emit(list(matched.values()))

            if len(matched) >= stop_target:
                break
            if not next_params:
                break

    pool = list(matched.values())
    rows_out = _sorted_rows(pool, req)

    if req.exclude_honeypots and pool:
        # Never run security inside the 45s per-page enrich budget.
        scan_n = min(len(pool), req.max_results + 200)
        ranked = sorted(
            pool,
            key=lambda r: _sort_key(r, req.sort_by),
            reverse=(req.sort_order == ScreenSortOrder.desc),
        )[:scan_n]
        await prog(
            "security",
            f"Honeypot check (GMGN) for {len(ranked)} tokens…",
            0.88,
        )
        try:
            checked = await asyncio.wait_for(
                _filter_honeypots(ranked),
                timeout=45.0,
            )
        except TimeoutError:
            logger.warning("Honeypot filter timed out — keeping candidates without GMGN filter")
            checked = ranked
        rows_out = _sorted_rows(checked, req)
        await emit(rows_out)

    await emit(rows_out)
    await prog("done", f"Done — {len(rows_out)} tokens", 1.0)
    return rows_out
