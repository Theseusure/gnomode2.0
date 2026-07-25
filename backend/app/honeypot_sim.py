"""On-chain buy→sell honeypot simulation for Robinhood Chain (ScanHood-style).

Uses vendored HoneypotSim bytecode via eth_call (constructor probe). The simulator
intentionally reverts with encoded (tokenGot, canSell, wethBack, wethIn).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode

from .blockscout import blockscout_api_base, blockscout_headers
from .chain import CallRevert, RpcClient, checksum, http_client
from .config import settings
from .constants import (
    UNI_V2_FACTORY,
    UNI_V2_ROUTER,
    UNI_V3_FACTORY,
    UNI_V3_ROUTER,
    V3_FEE_TIERS,
    WETH,
    ZERO,
)

logger = logging.getLogger(__name__)

_BYTECODE_PATH = Path(__file__).resolve().parent / "data" / "honeypot_sim_bytecode.txt"
_TEST_ETH_WEI = 10**16  # 0.01 ETH
_CACHE_TTL_S = 30 * 60
_CONCURRENCY = 12
_UNSAFE = frozenset({"HONEYPOT", "CANT_BUY", "HIGH_TAX"})

_sem = asyncio.Semaphore(_CONCURRENCY)
_cache: dict[str, tuple[float, "SimResult"]] = {}
_whale_lock = asyncio.Lock()
_resolved_whale: str | None = None
_init_code: str | None = None


@dataclass(frozen=True)
class SimResult:
    ok: bool
    verdict: str
    reason: str | None = None
    can_buy: bool = False
    can_sell: bool = False
    round_trip_loss_pct: float | None = None
    venue: str | None = None

    @property
    def blocked(self) -> bool:
        return self.verdict in _UNSAFE


def _load_init_code() -> str:
    global _init_code
    if _init_code is not None:
        return _init_code
    raw = _BYTECODE_PATH.read_text(encoding="utf-8").strip()
    if not raw.startswith("0x"):
        raw = "0x" + raw
    _init_code = raw
    return _init_code


async def _list_venues(rpc: RpcClient, token: str) -> list[dict[str, Any]]:
    """Return liquid WETH venues, highest liquidity first.

    Important: do NOT prefer an empty V2 pair over a live V3 pool — that yields
    false CANT_BUY and lets real honeypots on other venues slip through fail-open.
    """
    token_cs = checksum(token)
    weth = checksum(WETH)
    found: list[dict[str, Any]] = []

    try:
        pair = await rpc.get_v2_pair(token_cs, weth)
        if pair and pair.lower() != ZERO.lower():
            try:
                reserves = await rpc._call(
                    lambda p=pair: rpc.v2_pair(p).functions.getReserves().call()
                )
                r0, r1 = int(reserves[0]), int(reserves[1])
                score = r0 + r1
                if score > 0:
                    found.append(
                        {"is_v3": False, "fee": 0, "label": "V2", "score": float(score)}
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("V2 reserves failed: %r", exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("V2 venue lookup failed: %r", exc)

    for fee in (10000, 3000, 500, 100):
        try:
            pool = await rpc.get_v3_pool(token_cs, weth, fee)
            if not pool or pool.lower() == ZERO.lower():
                continue
            liq = await rpc._call(lambda p=pool: rpc.v3_pool(p).functions.liquidity().call())
            liq_i = int(liq)
            if liq_i > 0:
                found.append(
                    {
                        "is_v3": True,
                        "fee": fee,
                        "label": f"V3:{fee}",
                        "score": float(liq_i),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("V3 venue fee=%s failed: %r", fee, exc)

    found.sort(key=lambda v: v["score"], reverse=True)
    return found


async def _discover_whale(rpc: RpcClient) -> str | None:
    """Pick an EOА with ≥0.05 ETH from WETH holders (Blockscout)."""
    url = f"{blockscout_api_base()}/tokens/{checksum(WETH)}/holders"
    try:
        resp = await http_client().get(url, headers=blockscout_headers(), timeout=15.0)
        if resp.status_code != 200:
            logger.warning("Whale discovery Blockscout %s", resp.status_code)
            return None
        items = resp.json().get("items") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Whale discovery failed: %r", exc)
        return None

    min_wei = 5 * 10**16  # 0.05 ETH
    for item in items[:25]:
        addr_obj = item.get("address")
        if isinstance(addr_obj, dict):
            addr = addr_obj.get("hash") or ""
            is_contract = bool(addr_obj.get("is_contract"))
        else:
            addr = str(item.get("address_hash") or item.get("address") or "")
            is_contract = False
        if not addr.startswith("0x") or is_contract:
            continue
        try:
            bal = await rpc._call(lambda a=addr: rpc.w3.eth.get_balance(checksum(a)))
            if int(bal) >= min_wei:
                # Prefer EOAs
                if await rpc.is_eoa(addr):
                    return checksum(addr)
        except Exception:  # noqa: BLE001
            continue
    return None


async def get_sim_whale(rpc: RpcClient | None = None) -> str | None:
    global _resolved_whale
    configured = (settings.honeypot_sim_whale or "").strip()
    if configured:
        try:
            return checksum(configured)
        except Exception:  # noqa: BLE001
            logger.warning("Invalid HONEYPOT_SIM_WHALE=%r", configured)

    if _resolved_whale:
        return _resolved_whale

    async with _whale_lock:
        if _resolved_whale:
            return _resolved_whale
        client = rpc or RpcClient()
        found = await _discover_whale(client)
        if found:
            _resolved_whale = found
            logger.info("Honeypot sim whale auto-resolved: %s", found)
        else:
            logger.warning("No honeypot sim whale available — simulation will fail-open")
        return _resolved_whale


def _decode_sim_revert(data: str | None) -> SimResult | None:
    if not data or not isinstance(data, str):
        return None
    hexdata = data[2:] if data.startswith("0x") else data
    # Strip Error(string) / Panic selectors if present — ScanHood returns raw abi tuple.
    # Sometimes wrapped as Error(string) with hex inside; try direct decode first.
    try:
        raw = bytes.fromhex(hexdata)
    except ValueError:
        return None

    # If standard Error(string) selector 0x08c379a0 — not our format
    if len(raw) >= 4 and raw[:4].hex() == "08c379a0":
        return None

    # Payload is 4×32 = 128 bytes. Nodes may prefix a 4-byte selector.
    if len(raw) >= 132:
        raw = raw[-128:]
    elif len(raw) >= 128:
        raw = raw[:128]
    else:
        return None

    try:
        token_got, can_sell_u8, weth_back, weth_in = abi_decode(
            ["uint256", "uint8", "uint256", "uint256"],
            raw,
        )
    except Exception:  # noqa: BLE001
        return None

    can_buy = int(token_got) > 0
    sellable = int(can_sell_u8) == 1 and int(weth_back) > 0
    if int(weth_in) > 0:
        loss_pct = (1.0 - (int(weth_back) / int(weth_in))) * 100.0
    else:
        loss_pct = 100.0

    if not can_buy:
        verdict = "CANT_BUY"
    elif not sellable:
        verdict = "HONEYPOT"
    elif loss_pct > 50:
        verdict = "HIGH_TAX"
    elif loss_pct > 25:
        verdict = "TAXED"
    else:
        verdict = "SAFE"

    return SimResult(
        ok=True,
        verdict=verdict,
        can_buy=can_buy,
        can_sell=sellable,
        round_trip_loss_pct=round(loss_pct, 1),
    )


async def _sim_on_venue(
    rpc: RpcClient,
    token: str,
    venue: dict[str, Any],
    whale: str,
    init: str,
) -> SimResult:
    args = abi_encode(
        ["address", "address", "address", "address", "bool", "uint24"],
        [
            checksum(WETH),
            checksum(token),
            checksum(UNI_V2_ROUTER),
            checksum(UNI_V3_ROUTER),
            bool(venue["is_v3"]),
            int(venue["fee"]),
        ],
    )
    tx = {
        "from": whale,
        "data": init + args.hex(),
        "value": hex(_TEST_ETH_WEI),
    }
    try:
        await rpc.eth_call_raw(tx)
        return SimResult(
            ok=False,
            verdict="ERROR",
            reason="sim did not revert as expected",
            venue=venue["label"],
        )
    except CallRevert as exc:
        decoded = _decode_sim_revert(exc.data)
        if decoded is None:
            return SimResult(
                ok=False,
                verdict="ERROR",
                reason=f"no sim data: {str(exc)[:80]}",
                venue=venue["label"],
            )
        return SimResult(
            ok=decoded.ok,
            verdict=decoded.verdict,
            reason=decoded.reason,
            can_buy=decoded.can_buy,
            can_sell=decoded.can_sell,
            round_trip_loss_pct=decoded.round_trip_loss_pct,
            venue=venue["label"],
        )


async def scan_token(token: str, rpc: RpcClient | None = None) -> SimResult:
    """Run buy→sell simulation across liquid venues until decisive."""
    key = token.lower()
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL_S:
        return hit[1]

    client = rpc or RpcClient()

    async with _sem:
        venues = await _list_venues(client, token)
        if not venues:
            res = SimResult(ok=False, verdict="NO_POOL", reason="no WETH pool with liquidity")
            _cache[key] = (now, res)
            return res

        whale = await get_sim_whale(client)
        if not whale:
            return SimResult(ok=False, verdict="ERROR", reason="no funded sim whale")

        try:
            init = _load_init_code()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Honeypot bytecode load failed: %r", exc)
            return SimResult(ok=False, verdict="ERROR", reason="bytecode missing")

        last = SimResult(ok=False, verdict="ERROR", reason="no venue attempted")
        for venue in venues:
            try:
                res = await _sim_on_venue(client, token, venue, whale, init)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Honeypot sim error %s %s: %r", key[:12], venue["label"], exc)
                last = SimResult(
                    ok=False,
                    verdict="ERROR",
                    reason=str(exc)[:120],
                    venue=venue["label"],
                )
                continue

            last = res
            # Empty/wrong venue → try next liquid pool
            if res.verdict in {"CANT_BUY", "ERROR"}:
                continue
            # SAFE / TAXED / HONEYPOT / HIGH_TAX are decisive
            _cache[key] = (now, res)
            return res

        # All venues CANT_BUY or ERROR
        if last.verdict == "CANT_BUY" or last.ok:
            _cache[key] = (now, last)
        return last


async def scan_tokens(addresses: list[str], rpc: RpcClient | None = None) -> dict[str, SimResult]:
    client = rpc or RpcClient()
    uniq = list(dict.fromkeys(a.lower() for a in addresses if a))
    results = await asyncio.gather(*(scan_token(a, client) for a in uniq))
    return {a: r for a, r in zip(uniq, results, strict=False)}


# Silence unused — factories used via RpcClient helpers
_ = (UNI_V2_FACTORY, UNI_V3_FACTORY, V3_FEE_TIERS)
