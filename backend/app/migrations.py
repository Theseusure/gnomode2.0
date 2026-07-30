"""Confirmed Pons/Flap migrations, ported from Launch Radar.

Pons comes from the official graduated catalog with a per-request cache key.
Flap comes from the Portal ``LaunchedToDEX`` event. Token/pool discovery events
are deliberately not treated as migrations.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from .chain import http_client

PONS_URL = "https://robinhood.ponslaunchpad.com/api/pons-launches/graduations"
BLOCKSCOUT_LOGS = "https://robinhoodchain.blockscout.com/api"
DEXSCREENER = "https://api.dexscreener.com/tokens/v1/robinhood"
FLAP_PORTAL = "0x26605f322f7fF986f381bB9A6e3f5DAb0bEaEb09"
FLAP_LAUNCHED_TOPIC = "0x6e4f47630b8745b8cacbd44f42a8a33e7eea7cc08ef22fc7630f4f385784ff7d"


def _iso(raw: Any) -> str | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(
            timezone.utc
        ).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _pons(row: dict[str, Any]) -> dict[str, Any] | None:
    token = str(row.get("token") or "")
    if not row.get("graduated") or len(token) != 42:
        return None
    return {
        "launchpad": "pons",
        "address": token,
        "name": row.get("name"),
        "symbol": row.get("symbol"),
        "image_url": row.get("logo"),
        "migrated_at": _iso(row.get("graduatedAt")),
        "pool_address": row.get("pool"),
        "source_url": f"https://www.ponsfamily.com/launchpad/{token}",
        "verification": "official_indexer",
    }


def _flap(row: dict[str, Any]) -> dict[str, Any] | None:
    data = str(row.get("data") or "").removeprefix("0x")
    if len(data) < 128:
        return None
    token = "0x" + data[24:64]
    pool = "0x" + data[88:128]
    raw_ts = row.get("timeStamp")
    try:
        ts = int(str(raw_ts), 16) if str(raw_ts).startswith("0x") else int(str(raw_ts))
        migrated_at = datetime.fromtimestamp(ts, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    except (TypeError, ValueError):
        migrated_at = None
    tx = str(row.get("transactionHash") or "")
    return {
        "launchpad": "flap",
        "address": token,
        "name": None,
        "symbol": None,
        "image_url": None,
        "migrated_at": migrated_at,
        "pool_address": pool,
        "source_url": f"https://robinhoodchain.blockscout.com/tx/{tx}",
        "verification": "onchain",
    }


async def _fetch_pons() -> list[dict[str, Any]]:
    response = await http_client().get(
        PONS_URL,
        params={"catalog": "1", "v": str(int(time.time() * 1000))},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return [token for row in data if isinstance(row, dict) and (token := _pons(row))]


async def _fetch_flap() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(1, 51):
        response = await http_client().get(
            BLOCKSCOUT_LOGS,
            params={
                "module": "logs",
                "action": "getLogs",
                "fromBlock": "4180724",
                "toBlock": "latest",
                "address": FLAP_PORTAL,
                "topic0": FLAP_LAUNCHED_TOPIC,
                "page": str(page),
                "offset": "1000",
            },
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("result") if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            break
        out.extend(token for row in rows if isinstance(row, dict) and (token := _flap(row)))
        if len(rows) < 1000:
            break
    return out


async def _enrich(tokens: list[dict[str, Any]]) -> None:
    for offset in range(0, len(tokens), 30):
        batch = tokens[offset : offset + 30]
        response = await http_client().get(
            f"{DEXSCREENER}/{','.join(row['address'] for row in batch)}", timeout=15
        )
        if response.status_code != 200:
            continue
        pairs = response.json()
        if not isinstance(pairs, list):
            continue
        for token in batch:
            address = token["address"].lower()
            matched = [
                pair
                for pair in pairs
                if address
                in (
                    str((pair.get("baseToken") or {}).get("address") or "").lower(),
                    str((pair.get("quoteToken") or {}).get("address") or "").lower(),
                )
            ]
            if not matched:
                continue
            pair = max(
                matched,
                key=lambda item: float((item.get("liquidity") or {}).get("usd") or 0),
            )
            base = pair.get("baseToken") or {}
            quote = pair.get("quoteToken") or {}
            asset = (
                base
                if str(base.get("address") or "").lower() == address
                else quote
            )
            txns = (pair.get("txns") or {}).get("h24") or {}
            token["name"] = token.get("name") or asset.get("name")
            token["symbol"] = token.get("symbol") or asset.get("symbol")
            token["image_url"] = token.get("image_url") or (pair.get("info") or {}).get(
                "imageUrl"
            )
            token["liquidity_usd"] = float(
                (pair.get("liquidity") or {}).get("usd") or 0
            )
            token["traders_24h"] = int(txns.get("buys") or 0) + int(
                txns.get("sells") or 0
            )


async def migrated_tokens(
    launchpads: set[str],
    max_age_hours: float | None = None,
    min_liquidity_usd: float | None = None,
    max_liquidity_usd: float | None = None,
    min_traders_24h: int | None = None,
    max_traders_24h: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    tasks: list[tuple[str, Any]] = []
    if "pons" in launchpads:
        tasks.append(("pons", _fetch_pons()))
    if "flap" in launchpads:
        tasks.append(("flap", _fetch_flap()))
    settled = await asyncio.gather(
        *(task for _, task in tasks), return_exceptions=True
    )
    errors: dict[str, str] = {}
    tokens: list[dict[str, Any]] = []
    for (name, _), result in zip(tasks, settled, strict=True):
        if isinstance(result, BaseException):
            errors[name] = str(result)
        else:
            tokens.extend(result)
    by_key = {
        (row["launchpad"], row["address"].lower()): row for row in tokens
    }
    tokens = list(by_key.values())
    if max_age_hours is not None:
        cutoff = time.time() - max_age_hours * 3600
        tokens = [
            row
            for row in tokens
            if row.get("migrated_at")
            and datetime.fromisoformat(row["migrated_at"].replace("Z", "+00:00")).timestamp()
            >= cutoff
        ]
    await _enrich(tokens)

    def inside(value: float, low: float | None, high: float | None) -> bool:
        return (low is None or value >= low) and (high is None or value <= high)

    tokens = [
        row
        for row in tokens
        if inside(
            float(row.get("liquidity_usd") or 0),
            min_liquidity_usd,
            max_liquidity_usd,
        )
        and inside(
            float(row.get("traders_24h") or 0),
            min_traders_24h,
            max_traders_24h,
        )
    ]
    tokens.sort(key=lambda row: row.get("migrated_at") or "", reverse=True)
    return tokens, errors
