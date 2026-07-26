"""Periodic tired-gnome status messages to Telegram."""

from __future__ import annotations

import asyncio
import logging
import random
import time

from .gnome_phrases import pick_gnome_phrase
from .telegram import resolve_chat_id, resolve_topic_id, send_message, telegram_configured
from .watch_store import WatchStore, watch_store

logger = logging.getLogger(__name__)

# Random gap between banter messages while watch is enabled.
_MIN_INTERVAL_SEC = 10 * 60
_MAX_INTERVAL_SEC = 15 * 60


class GnomeBanter:
    def __init__(self, store: WatchStore | None = None) -> None:
        self._store = store or watch_store
        self._last_phrase: str | None = None
        self._next_ts: float | None = None
        self._wake = asyncio.Event()

    def notify_config_changed(self) -> None:
        self._wake.set()

    def status_bits(self) -> dict:
        cfg = self._store.load_config()
        return {
            "gnome_banter_enabled": bool(getattr(cfg, "gnome_banter_enabled", True)),
            "gnome_banter_next_ts": self._next_ts,
        }

    async def run_loop(self) -> None:
        logger.info("Gnome banter loop started (%s–%ss)", _MIN_INTERVAL_SEC, _MAX_INTERVAL_SEC)
        while True:
            cfg = self._store.load_config()
            banter_on = bool(getattr(cfg, "gnome_banter_enabled", True))
            chat = resolve_chat_id(cfg.telegram_chat_id)
            ready = cfg.enabled and banter_on and telegram_configured(chat)

            if not ready:
                self._next_ts = None
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5.0)
                except TimeoutError:
                    pass
                continue

            delay = random.randint(_MIN_INTERVAL_SEC, _MAX_INTERVAL_SEC)
            self._next_ts = time.time() + delay
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
                # Woken early (config change) — re-evaluate without sending.
                continue
            except TimeoutError:
                pass

            cfg = self._store.load_config()
            banter_on = bool(getattr(cfg, "gnome_banter_enabled", True))
            chat = resolve_chat_id(cfg.telegram_chat_id)
            if not (cfg.enabled and banter_on and telegram_configured(chat)):
                continue

            try:
                topic_id = resolve_topic_id(cfg.telegram_topic_id)
            except RuntimeError as exc:
                logger.warning("Gnome banter skipped: %s", exc)
                continue

            phrase = pick_gnome_phrase(avoid=self._last_phrase)
            text = f"<i>{phrase}</i>"
            try:
                await send_message(chat, text, topic_id=topic_id)
                self._last_phrase = phrase
                logger.info("Gnome banter sent")
            except Exception:  # noqa: BLE001
                logger.exception("Gnome banter failed to send")


gnome_banter = GnomeBanter()
