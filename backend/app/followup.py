"""Follow-up runner: watch early buyers for 2nd/3rd new-token buys @ low mcap."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .blockscout import iter_address_token_transfers
from .config import settings
from .constants import QUOTE_TOKENS
from .followup_store import FollowupStore, followup_store
from .models import (
    BuyerRow,
    FollowupConfig,
    FollowupStatus,
    JobLogEntry,
)
from .pools import fetch_dexscreener_pairs
from .raybot import RayBotClient, raybot_client, raybot_configured
from .telegram import (
    resolve_chat_id,
    resolve_topic_id,
    send_followup_deal,
    telegram_configured,
)

logger = logging.getLogger(__name__)

_LOG_MAX = 300


def _addr_hash(node: object) -> str:
    if isinstance(node, dict):
        return str(node.get("hash") or node.get("address_hash") or "").lower()
    return str(node or "").lower()


def _is_contract(node: object) -> bool:
    return isinstance(node, dict) and bool(node.get("is_contract"))


def _token_meta(item: dict[str, Any]) -> tuple[str, str]:
    tok = item.get("token") or {}
    addr = str(tok.get("address") or tok.get("address_hash") or "").lower()
    sym = str(tok.get("symbol") or "")
    return addr, sym


def should_alert_deal(
    deal_index: int,
    mcap_at_buy: float | None,
    *,
    max_mcap_alert: float,
    alert_on_deals: list[int],
    min_mcap_alert: float | None = None,
    bought_usd: float | None = None,
    min_bought_usd: float | None = None,
    max_bought_usd: float | None = None,
) -> bool:
    """True only for configured deal indices that pass native filter set.

    Mirrors RayBot-style gates without external RayBot:
    - deal index in alert_on_deals (default 2, 3)
    - mcap ≤ max_mcap_alert (high mcap → no alert)
    - optional mcap ≥ min_mcap_alert
    - optional bought_usd min/max when value is known
    """
    if deal_index not in alert_on_deals:
        return False
    if mcap_at_buy is None:
        return False
    mcap = float(mcap_at_buy)
    if mcap > float(max_mcap_alert):
        return False
    if min_mcap_alert is not None and mcap < float(min_mcap_alert):
        return False
    if bought_usd is not None:
        usd = float(bought_usd)
        if min_bought_usd is not None and usd < float(min_bought_usd):
            return False
        if max_bought_usd is not None and usd > float(max_bought_usd):
            return False
    elif min_bought_usd is not None:
        # Require known size when min filter is set
        return False
    return True


def alert_kwargs_from_config(cfg: FollowupConfig) -> dict:
    return {
        "max_mcap_alert": cfg.max_mcap_alert,
        "alert_on_deals": list(cfg.alert_on_deals or [2, 3]),
        "min_mcap_alert": cfg.min_mcap_alert,
        "min_bought_usd": cfg.min_bought_usd,
        "max_bought_usd": cfg.max_bought_usd,
    }


async def estimate_token_quote(token: str) -> tuple[float | None, float | None]:
    """Return (market_cap_usd, price_usd) from the highest-liquidity DexScreener pair."""
    pairs = await fetch_dexscreener_pairs(token)
    if not pairs:
        return None, None
    best_mcap: float | None = None
    best_price: float | None = None
    best_liq = -1.0
    for p in pairs:
        try:
            liq = float((p.get("liquidity") or {}).get("usd") or 0.0)
        except (TypeError, ValueError):
            liq = 0.0
        raw = p.get("marketCap")
        if raw is None:
            raw = p.get("fdv")
        try:
            mcap = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            mcap = None
        try:
            price = float(p.get("priceUsd")) if p.get("priceUsd") is not None else None
        except (TypeError, ValueError):
            price = None
        if mcap is None and price is None:
            continue
        if liq >= best_liq:
            best_liq = liq
            best_mcap = mcap
            best_price = price
    return best_mcap, best_price


async def estimate_token_mcap(token: str) -> float | None:
    mcap, _ = await estimate_token_quote(token)
    return mcap


def _transfer_token_amount(item: dict[str, Any]) -> float | None:
    """Parse human token amount from a Blockscout token-transfer item."""
    total = item.get("total")
    raw: str | None = None
    decimals: int | None = None
    if isinstance(total, dict):
        raw = total.get("value")
        if raw is None:
            raw = total.get("token_id")
        try:
            decimals = int(total.get("decimals")) if total.get("decimals") is not None else None
        except (TypeError, ValueError):
            decimals = None
    elif total is not None:
        raw = str(total)
    if decimals is None:
        tok = item.get("token") or {}
        if isinstance(tok, dict) and tok.get("decimals") is not None:
            try:
                decimals = int(tok["decimals"])
            except (TypeError, ValueError):
                decimals = None
    if raw is None:
        return None
    try:
        value = float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if decimals is None:
        decimals = 18
    if decimals < 0:
        return None
    return value / (10**decimals)


def estimate_bought_usd(item: dict[str, Any], price_usd: float | None) -> float | None:
    if price_usd is None or price_usd <= 0:
        return None
    amount = _transfer_token_amount(item)
    if amount is None or amount <= 0:
        return None
    return amount * float(price_usd)


def _is_buy_like_transfer(
    item: dict[str, Any],
    wallet: str,
    *,
    buys_only: bool,
    track_transfers: bool,
) -> bool:
    """RayBot-style EVM gate: inbound to tracked wallet; optionally DEX-only."""
    to_h = _addr_hash(item.get("to"))
    if to_h != wallet.lower():
        return False
    frm = item.get("from")
    from_contract = _is_contract(frm)
    if buys_only:
        # DEX/router/pool sends tokens to wallet
        return from_contract
    if from_contract:
        return True
    # EOA → wallet transfer
    return bool(track_transfers)


class FollowupRunner:
    def __init__(self, store: FollowupStore | None = None) -> None:
        self._store = store or followup_store
        self._raybot: RayBotClient = raybot_client
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._force_run = False
        self._stop_requested = False
        self._running = False
        self._next_run_ts: float | None = None
        self._last_run_ts: float | None = None
        self._last_run_duration_sec: float | None = None
        self._last_error: str | None = None
        self._last_message: str = ""
        self._last_checked = 0
        self._last_new_deals = 0
        self._last_alerts_sent = 0
        self._log: list[JobLogEntry] = []

    def _append_log(self, stage: str, message: str, *, percent: float = 0.0) -> None:
        entry = JobLogEntry(
            ts=time.time(), stage=stage, message=message, percent=percent
        )
        if self._log:
            last = self._log[-1]
            if last.stage == entry.stage and last.message == entry.message:
                self._log[-1] = entry
                return
        self._log.append(entry)
        if len(self._log) > _LOG_MAX:
            self._log = self._log[-_LOG_MAX:]

    def notify_config_changed(self) -> None:
        self._wake.set()

    def status(self) -> FollowupStatus:
        from .followup_bot import followup_bot

        cfg = self._store.load_config()
        watching, done = self._store.counts()
        chat = resolve_chat_id(cfg.telegram_chat_id)
        return FollowupStatus(
            enabled=cfg.enabled,
            running=self._running,
            telegram_configured=telegram_configured(chat),
            bot_commands_enabled=cfg.bot_commands_enabled,
            bot_polling=followup_bot.polling,
            raybot_configured=raybot_configured() and cfg.raybot_enabled,
            next_run_ts=self._next_run_ts,
            last_run_ts=self._last_run_ts,
            last_run_duration_sec=self._last_run_duration_sec,
            last_error=self._last_error,
            last_message=self._last_message,
            wallets_watching=watching,
            wallets_done=done,
            last_checked=self._last_checked,
            last_new_deals=self._last_new_deals,
            last_alerts_sent=self._last_alerts_sent,
            stop_requested=self._stop_requested,
            log=list(self._log),
        )

    def reset_counters(self) -> FollowupStatus:
        self._last_error = None
        self._last_message = ""
        self._last_checked = 0
        self._last_new_deals = 0
        self._last_alerts_sent = 0
        self._log.clear()
        return self.status()

    async def stop(self) -> FollowupStatus:
        self._stop_requested = True
        self._wake.set()
        return self.status()

    async def run_now(self) -> FollowupStatus:
        self._force_run = True
        self._stop_requested = False
        self._wake.set()
        return self.status()

    async def run_loop(self) -> None:
        while True:
            cfg = self._store.load_config()
            if not cfg.enabled and not self._force_run:
                self._next_run_ts = None
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
                continue

            self._force_run = False
            self._stop_requested = False
            started = time.time()
            self._running = True
            self._next_run_ts = None
            try:
                await self.run_cycle(cfg)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Follow-up cycle failed")
                self._last_error = str(exc)
                self._last_message = f"Ошибка: {exc}"
                self._append_log("error", self._last_message)
            finally:
                self._running = False
                self._last_run_ts = time.time()
                self._last_run_duration_sec = self._last_run_ts - started

            cfg = self._store.load_config()
            if not cfg.enabled:
                continue
            self._next_run_ts = time.time() + cfg.interval_sec
            self._wake.clear()
            while True:
                remaining = self._next_run_ts - time.time()
                if remaining <= 0 or self._force_run or self._stop_requested:
                    break
                try:
                    await asyncio.wait_for(
                        self._wake.wait(), timeout=min(remaining, 30.0)
                    )
                except asyncio.TimeoutError:
                    pass
                if self._wake.is_set():
                    self._wake.clear()
                    cfg = self._store.load_config()
                    if not cfg.enabled and not self._force_run:
                        break

    async def run_cycle(self, cfg: FollowupConfig | None = None) -> None:
        async with self._lock:
            await self._cycle_body(cfg or self._store.load_config())

    async def ingest_from_watch(
        self,
        buyers: list[BuyerRow],
        *,
        cfg: FollowupConfig | None = None,
    ) -> int:
        """Called from watch after successful Telegram send of early buyers."""
        cfg = cfg or self._store.load_config()
        if not cfg.ingest_from_watch:
            return 0
        inserted = self._store.ingest_buyers(
            buyers,
            max_deals=cfg.max_deals,
            max_mcap_alert=cfg.max_mcap_alert,
        )
        if not inserted:
            return 0
        self._append_log(
            "ingest",
            f"В follow-up добавлено {len(inserted)} сделок",
        )

        # RayBot: sync wallets that just got deal #1 (new watchlist members)
        new_addrs = sorted({d.wallet for d in inserted if d.deal_index == 1})
        if cfg.raybot_enabled and new_addrs and raybot_configured():
            try:
                synced = await self._raybot.sync_wallets_low_mcap(
                    new_addrs, max_mcap_alert=cfg.max_mcap_alert
                )
                self._store.mark_raybot_synced(synced, True)
                self._append_log(
                    "raybot",
                    f"RayBot sync: {len(synced)}/{len(new_addrs)}",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("RayBot sync failed: %s", exc)
                self._append_log("raybot", f"RayBot sync ошибка: {exc}")

        # Alert immediately if watch itself produced deal #2/#3 @ low mcap
        chat = resolve_chat_id(cfg.telegram_chat_id)
        topic_id = resolve_topic_id(cfg.telegram_topic_id)
        if telegram_configured(chat):
            for deal in inserted:
                if not should_alert_deal(
                    deal.deal_index,
                    deal.mcap_at_buy,
                    bought_usd=deal.bought_usd,
                    **alert_kwargs_from_config(cfg),
                ):
                    continue
                if not self._store.mark_notified(deal.wallet, deal.token):
                    continue
                try:
                    await send_followup_deal(
                        chat,
                        wallet=deal.wallet,
                        token=deal.token,
                        token_symbol=deal.token_symbol,
                        deal_index=deal.deal_index,
                        mcap_at_buy=deal.mcap_at_buy,
                        bought_usd=deal.bought_usd,
                        topic_id=topic_id,
                    )
                    self._append_log(
                        "telegram",
                        f"Алерт deal #{deal.deal_index} (из автопарса)",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Follow-up alert failed: %s", exc)
        return len(inserted)

    async def _cycle_body(self, cfg: FollowupConfig) -> None:
        wallets = self._store.list_watching()
        self._last_checked = len(wallets)
        self._last_new_deals = 0
        self._last_alerts_sent = 0
        self._last_error = None
        if not wallets:
            self._last_message = "Нет кошельков в статусе watching"
            self._append_log("idle", self._last_message)
            return

        chat = resolve_chat_id(cfg.telegram_chat_id)
        topic_id = resolve_topic_id(cfg.telegram_topic_id)
        tg_ok = telegram_configured(chat)
        gate = alert_kwargs_from_config(cfg)

        self._last_message = f"Проверка {len(wallets)} кош…"
        self._append_log("scan", self._last_message, percent=5)

        for i, wallet in enumerate(wallets):
            if self._stop_requested:
                self._last_message = "Остановлено"
                self._append_log("stop", self._last_message)
                break
            try:
                new_deals = await self._scan_wallet(wallet, cfg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Follow-up scan %s: %s", wallet[:10], exc)
                continue

            for deal in new_deals:
                self._last_new_deals += 1
                if not should_alert_deal(
                    deal.deal_index,
                    deal.mcap_at_buy,
                    bought_usd=deal.bought_usd,
                    **gate,
                ):
                    self._append_log(
                        "skip",
                        f"{wallet[:10]}… deal #{deal.deal_index} "
                        f"mcap={deal.mcap_at_buy} — без алерта",
                    )
                    continue
                if not tg_ok:
                    self._last_error = "Telegram не настроен"
                    continue
                if not self._store.mark_notified(deal.wallet, deal.token):
                    continue
                try:
                    await send_followup_deal(
                        chat,
                        wallet=deal.wallet,
                        token=deal.token,
                        token_symbol=deal.token_symbol,
                        deal_index=deal.deal_index,
                        mcap_at_buy=deal.mcap_at_buy,
                        bought_usd=deal.bought_usd,
                        topic_id=topic_id,
                    )
                    self._last_alerts_sent += 1
                    self._append_log(
                        "telegram",
                        f"Алерт deal #{deal.deal_index} · {deal.token_symbol or deal.token[:10]}",
                    )
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    self._append_log("error", f"Telegram: {exc}")

            pct = 5 + 90 * (i + 1) / max(len(wallets), 1)
            self._last_message = (
                f"Проверено {i + 1}/{len(wallets)}, "
                f"новых сделок {self._last_new_deals}, алертов {self._last_alerts_sent}"
            )
            if (i + 1) % 5 == 0 or i + 1 == len(wallets):
                self._append_log("scan", self._last_message, percent=pct)

        self._last_message = (
            f"Готово — {self._last_checked} кош., "
            f"{self._last_new_deals} сделок, {self._last_alerts_sent} алертов"
        )
        self._append_log("done", self._last_message, percent=100)

    async def _scan_wallet(self, wallet: str, cfg: FollowupConfig) -> list:
        known = self._store.known_tokens(wallet)
        # Collect first matching inbound transfer per unknown token.
        # API is newest-first: keep overwriting so last seen (older) wins in scanned pages.
        candidates: dict[str, tuple[str, str, dict[str, Any]]] = {}
        async for item in iter_address_token_transfers(wallet, max_pages=6):
            token, sym = _token_meta(item)
            if not token or token in QUOTE_TOKENS or token in known:
                continue
            if not _is_buy_like_transfer(
                item,
                wallet,
                buys_only=cfg.buys_only,
                track_transfers=cfg.track_transfers,
            ):
                continue
            tx = str(item.get("transaction_hash") or item.get("tx_hash") or "")
            candidates[token] = (sym, tx, item)

        out = []
        for token, (sym, tx, item) in candidates.items():
            if self._stop_requested:
                break
            if token in self._store.known_tokens(wallet):
                continue
            mcap, price = await estimate_token_quote(token)
            bought_usd = estimate_bought_usd(item, price)
            deal = self._store.record_deal(
                wallet=wallet,
                token=token,
                token_symbol=sym,
                mcap_at_buy=mcap,
                bought_usd=bought_usd,
                tx_hash=tx,
                max_deals=cfg.max_deals,
            )
            if deal:
                out.append(deal)
        return out


followup_runner = FollowupRunner()
