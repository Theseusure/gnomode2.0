"""GMGN token security for Robinhood Chain (same source as gmgn.ai UI).

Uses the public web endpoint:
  GET /api/v1/token_security_evm/robinhood/{address}

Fast (~2s for 20 tokens) and matches what users see on GMGN.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CHAIN = "robinhood"
_BASE = f"https://gmgn.ai/api/v1/token_security_evm/{_CHAIN}"
_CONCURRENCY = 16
_CACHE_TTL_S = 10 * 60
_CLIENT_ID = "gmgn_web_gnomode"
_APP_VER = "20260725-gnomode"

_cache: dict[str, tuple[float, "GmgnSecurity"]] = {}
_sem = asyncio.Semaphore(_CONCURRENCY)
_http: httpx.AsyncClient | None = None


@dataclass(frozen=True)
class GmgnSecurity:
    address: str
    is_honeypot: bool | None  # True / False / None (unknown)
    is_show_alert: bool = False
    buy_tax: float | None = None
    sell_tax: float | None = None
    flags: tuple[str, ...] = ()
    reason: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def blocked(self) -> bool:
        return self.is_honeypot is True


def _truthy_honeypot(data: dict[str, Any]) -> bool | None:
    """GMGN uses is_honeypot bool/null and honeypot 1/0/-1."""
    hp = data.get("is_honeypot")
    if hp is True or hp == 1 or str(hp).lower() in {"1", "true", "yes"}:
        return True
    if hp is False or hp == 0 or str(hp).lower() in {"0", "false", "no"}:
        return False
    code = data.get("honeypot")
    try:
        n = int(code)
    except (TypeError, ValueError):
        return None
    if n == 1:
        return True
    if n == 0:
        return False
    return None  # -1 unknown


def _tax(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    # GMGN sometimes returns ratio (0.01) sometimes percent-ish strings
    if n > 1.0:
        n = n / 100.0
    return n


def classify(address: str, data: dict[str, Any] | None) -> GmgnSecurity:
    addr = address.lower()
    if not data:
        return GmgnSecurity(address=addr, is_honeypot=None, reason=None, raw=None)

    is_hp = _truthy_honeypot(data)
    flags = tuple(str(x) for x in (data.get("flags") or []) if x)
    alert = bool(data.get("is_show_alert"))
    buy = _tax(data.get("buy_tax"))
    sell = _tax(data.get("sell_tax"))

    reason: str | None = None
    if is_hp is True:
        reason = "gmgn:honeypot"
    elif sell is not None and sell >= 0.10:
        reason = f"gmgn:sell_tax={sell:.0%}"
        is_hp = True
    elif buy is not None and buy >= 0.10:
        reason = f"gmgn:buy_tax={buy:.0%}"
        is_hp = True
    # is_show_alert alone is too noisy on RH — only trust explicit honeypot/tax
    return GmgnSecurity(
        address=addr,
        is_honeypot=is_hp,
        is_show_alert=alert,
        buy_tax=buy,
        sell_tax=sell,
        flags=flags,
        reason=reason,
        raw=data,
    )


def _device_params() -> dict[str, str]:
    device = str(uuid.uuid4())
    fp = hashlib.md5(device.encode(), usedforsecurity=False).hexdigest()
    return {
        "device_id": device,
        "fp_did": fp,
        "client_id": _CLIENT_ID,
        "from_app": "gmgn",
        "app_ver": _APP_VER,
        "tz_name": "UTC",
        "tz_offset": "0",
        "app_lang": "en-US",
        "os": "web",
        "worker": "0",
    }


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=6.0),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://gmgn.ai",
                "Referer": "https://gmgn.ai/",
            },
            follow_redirects=True,
            limits=httpx.Limits(max_connections=24, max_keepalive_connections=12),
        )
    return _http


async def _fetch_one(address: str) -> GmgnSecurity:
    key = address.lower()
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]

    async with _sem:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = await _client().get(
                    f"{_BASE}/{key}",
                    params=_device_params(),
                )
                if resp.status_code in {403, 429, 502, 503}:
                    await asyncio.sleep(0.35 * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    logger.warning(
                        "GMGN security %s for %s: %s",
                        resp.status_code,
                        key[:12],
                        resp.text[:120],
                    )
                    result = GmgnSecurity(key, None)
                    _cache[key] = (now, result)
                    return result
                payload = resp.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                result = classify(key, data if isinstance(data, dict) else None)
                _cache[key] = (now, result)
                return result
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                await asyncio.sleep(0.25 * (attempt + 1))

        logger.warning("GMGN security failed for %s: %r", key[:12], last_err)
        result = GmgnSecurity(key, None)
        _cache[key] = (now, result)
        return result


async def check_token_security(address: str) -> GmgnSecurity:
    return await _fetch_one(address)


async def check_tokens_security(addresses: list[str]) -> dict[str, GmgnSecurity]:
    uniq = list(dict.fromkeys(a.lower() for a in addresses if a))
    if not uniq:
        return {}
    results = await asyncio.gather(*(_fetch_one(a) for a in uniq))
    return {r.address: r for r in results}


async def honeypot_reason(address: str) -> str | None:
    sec = await check_token_security(address)
    if sec.blocked:
        return sec.reason or "gmgn:honeypot"
    return None
