"""RayBot public API client — sync wallets + EVM MC filters.

Docs: https://docs.raybot.app/start/dev/api.md
Robinhood wallets are tracked via EVM (Ethereum) mode in RayBot.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_RATE_WINDOW = 10.0
_RATE_MAX = 5
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def raybot_configured() -> bool:
    return bool(
        (settings.raybot_api_user or "").strip()
        and (settings.raybot_api_token or "").strip()
    )


class RayBotClient:
    """Thin client with in-process rate limiting (5 req / 10s)."""

    def __init__(
        self,
        *,
        api_user: str | None = None,
        token: str | None = None,
        bot: int | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_user = (api_user if api_user is not None else settings.raybot_api_user).strip()
        self.token = (token if token is not None else settings.raybot_api_token).strip()
        self.bot = int(bot if bot is not None else settings.raybot_bot)
        self.base_url = (base_url or settings.raybot_base_url).rstrip("/")
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    def configured(self) -> bool:
        return bool(self.api_user and self.token)

    def _params(self) -> dict[str, str]:
        return {"api_user": self.api_user, "token": self.token}

    async def _pace(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._timestamps = [t for t in self._timestamps if now - t < _RATE_WINDOW]
            if len(self._timestamps) >= _RATE_MAX:
                sleep_for = _RATE_WINDOW - (now - self._timestamps[0]) + 0.05
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < _RATE_WINDOW]
            self._timestamps.append(time.monotonic())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured():
            raise RuntimeError("RayBot не настроен (RAYBOT_API_USER / RAYBOT_API_TOKEN)")
        await self._pace()
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
            resp = await client.request(
                method, url, params=self._params(), json=json_body
            )
        if resp.status_code == 429:
            raise RuntimeError("RayBot rate limit (5 req / 10s)")
        if resp.status_code >= 400:
            body = resp.text[:300]
            raise RuntimeError(f"RayBot HTTP {resp.status_code}: {body}")
        if not resp.content:
            return {}
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(f"RayBot error: {data}")
        return data if isinstance(data, dict) else {"data": data}

    async def add_wallets(
        self,
        wallets: list[dict[str, str]],
        *,
        user_id: str | None = None,
        bot: int | None = None,
    ) -> dict[str, Any]:
        """Add up to 10 wallets per call."""
        if not wallets:
            return {"status": "ok", "wallets": []}
        chunk = wallets[:10]
        body = {
            "user_id": user_id or self.api_user,
            "bot": int(bot if bot is not None else self.bot),
            "wallets": chunk,
        }
        return await self._request("POST", "/publicapi/wallets/add", json_body=body)

    async def delete_wallets(
        self,
        addresses: list[str],
        *,
        user_id: str | None = None,
        bot: int | None = None,
    ) -> dict[str, Any]:
        if not addresses:
            return {"status": "ok", "deletedCount": 0}
        body = {
            "user_id": user_id or self.api_user,
            "bot": int(bot if bot is not None else self.bot),
            "wallets": addresses,
        }
        return await self._request("POST", "/publicapi/wallets/delete", json_body=body)

    async def update_wallet_settings(
        self,
        wallet_address: str,
        settings_map: dict[str, Any],
        *,
        user_id: str | None = None,
        bot: int | None = None,
    ) -> dict[str, Any]:
        body = {
            "user_id": user_id or self.api_user,
            "bot": int(bot if bot is not None else self.bot),
            "wallet_address": wallet_address,
            "settings": settings_map,
        }
        return await self._request("POST", "/publicapi/wallets/settings", json_body=body)

    @staticmethod
    def low_mcap_evm_settings(max_mcap_alert: float) -> dict[str, Any]:
        """Mirror RayBot EVM filters: buys only, MC cap, ignore noise."""
        return {
            "evm_buys": True,
            "evm_sells": False,
            "evm_swaps": False,
            "evm_transfers": False,
            "evm_other": False,
            "evm_tip": False,
            "evm_mc_trade_max": float(max_mcap_alert),
            "evm_mc_trade_min": 0,
        }

    async def sync_wallets_low_mcap(
        self,
        addresses: list[str],
        *,
        max_mcap_alert: float,
        name_prefix: str = "gnomode",
    ) -> list[str]:
        """Add wallets in batches of 10 and apply low-mcap EVM settings.

        Returns addresses successfully synced.
        """
        synced: list[str] = []
        filt = self.low_mcap_evm_settings(max_mcap_alert)
        for i in range(0, len(addresses), 10):
            batch = addresses[i : i + 10]
            payload = [
                {
                    "wallet_address": addr,
                    "wallet_name": f"{name_prefix} {addr[:8]}",
                }
                for addr in batch
            ]
            try:
                await self.add_wallets(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("RayBot add failed (%s): %s", len(batch), exc)
                continue
            for addr in batch:
                try:
                    await self.update_wallet_settings(addr, filt)
                    synced.append(addr)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("RayBot settings failed for %s: %s", addr[:10], exc)
                    # Still count as added even if settings partially fail
                    synced.append(addr)
        return synced

    async def test_connection(self) -> dict[str, Any]:
        """List page 1 of wallets as a connectivity check."""
        body = {
            "page": 1,
            "limit": 1,
            "bot": self.bot,
            "user_id": self.api_user,
        }
        data = await self._request("POST", "/publicapi/wallets/show", json_body=body)
        return {
            "ok": True,
            "bot": self.bot,
            "total": data.get("total"),
            "message": "RayBot API отвечает",
        }


raybot_client = RayBotClient()
