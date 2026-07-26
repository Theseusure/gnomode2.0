"""Lifecycle Telegram notices: start («За работу!») and death («гном умер…»)."""

from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
import traceback
from types import FrameType

from .telegram import (
    resolve_chat_id,
    resolve_topic_id,
    send_message,
    send_message_sync,
    telegram_configured,
)
from .watch_store import watch_store

logger = logging.getLogger(__name__)

_death_lock = threading.Lock()
_death_announced = False
_hooks_installed = False


def _target() -> tuple[str, int | None] | None:
    cfg = watch_store.load_config()
    chat = resolve_chat_id(cfg.telegram_chat_id)
    if not telegram_configured(chat):
        return None
    try:
        topic = resolve_topic_id(cfg.telegram_topic_id)
    except RuntimeError:
        topic = None
    return chat, topic


async def announce_work_start() -> None:
    """Call when auto-parse is (re)enabled or process starts with watch on."""
    target = _target()
    if not target:
        return
    chat, topic = target
    try:
        await send_message(chat, "<b>За работу!</b>", topic_id=topic)
        logger.info("Announced watch start to Telegram")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to announce «За работу!»")


def announce_death(reason: str, *, sync: bool = True) -> None:
    """Notify Telegram that the gnome/process died. Safe to call multiple times."""
    global _death_announced
    with _death_lock:
        if _death_announced:
            return
        _death_announced = True

    text_reason = (reason or "неизвестная причина").strip()
    if len(text_reason) > 800:
        text_reason = text_reason[:800] + "…"
    # Escape minimal HTML
    safe = (
        text_reason.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    msg = f"гном умер по причине: <code>{safe}</code>"

    target = _target()
    if not target:
        logger.warning("Death announce skipped — Telegram not configured (%s)", reason)
        return
    chat, topic = target

    try:
        if sync:
            send_message_sync(chat, msg, topic_id=topic)
        else:
            # Best-effort from async context without awaiting (shutdown may be mid-flight).
            send_message_sync(chat, msg, topic_id=topic)
        logger.info("Announced death to Telegram: %s", reason[:200])
    except Exception:  # noqa: BLE001
        logger.exception("Failed to announce gnome death")


async def announce_death_async(reason: str) -> None:
    global _death_announced
    with _death_lock:
        if _death_announced:
            return
        _death_announced = True

    text_reason = (reason or "неизвестная причина").strip()
    if len(text_reason) > 800:
        text_reason = text_reason[:800] + "…"
    safe = (
        text_reason.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    msg = f"гном умер по причине: <code>{safe}</code>"
    target = _target()
    if not target:
        return
    chat, topic = target
    try:
        await send_message(chat, msg, topic_id=topic)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to announce gnome death (async)")


def install_death_hooks() -> None:
    """Register process-level hooks once (signals, atexit, sys.excepthook)."""
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True

    prev_excepthook = sys.excepthook

    def _excepthook(exc_type, exc, tb) -> None:  # noqa: ANN001
        try:
            detail = "".join(traceback.format_exception(exc_type, exc, tb))
            # Prefer short message + last traceback lines
            short = f"{getattr(exc_type, '__name__', exc_type)}: {exc}"
            tail = "\n".join(detail.strip().splitlines()[-8:])
            announce_death(f"{short}\n{tail}")
        finally:
            prev_excepthook(exc_type, exc, tb)

    sys.excepthook = _excepthook

    def _atexit() -> None:
        announce_death("процесс завершён (atexit)")

    atexit.register(_atexit)

    def _signal_handler(signum: int, _frame: FrameType | None) -> None:
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        announce_death(f"сигнал {name}")
        # Restore default and re-raise so uvicorn can exit.
        signal.signal(signum, signal.SIG_DFL)
        signal.raise_signal(signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_handler)
        except Exception:  # noqa: BLE001
            logger.debug("Could not install handler for %s", sig, exc_info=True)
