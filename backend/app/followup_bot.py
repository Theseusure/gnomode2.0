"""Native Telegram follow-up bot (commands + filters) — replaces RayBot dependency.

Commands (same TELEGRAM_BOT_TOKEN as watch alerts):
  /start /help — справка
  /status — статус follow-up
  /wallets — список watching (кратко)
  /filters — текущие фильтры
  /on /off — включить/выключить цикл
  /run — запустить цикл сейчас
  /set_max_mcap <n> — порог max mcap алерта
  /set_min_mcap <n|off> — нижняя граница mcap
  /set_interval <sec> — интервал цикла
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .followup_store import followup_store
from .models import FollowupConfig
from .telegram import (
    TG_CLIENT_KW,
    bot_api_url,
    bot_token,
    resolve_chat_id,
    send_message,
)

logger = logging.getLogger(__name__)

_HELP = (
    "<b>gnomode Follow-up bot</b>\n"
    "Нативный трекер без RayBot.\n\n"
    "/status — статус цикла\n"
    "/wallets — кошельки watching\n"
    "/filters — фильтры алертов\n"
    "/on · /off — вкл/выкл follow-up\n"
    "/run — цикл сейчас\n"
    "/set_max_mcap 15000 — max mcap для алерта\n"
    "/set_min_mcap 0|off — min mcap\n"
    "/set_interval 300 — интервал сек\n"
    "/help — эта справка"
)


class FollowupBot:
    """Long-poll Telegram getUpdates for follow-up control commands."""

    def __init__(self) -> None:
        self._offset = 0
        self._polling = False
        self._task: asyncio.Task | None = None

    @property
    def polling(self) -> bool:
        return self._polling

    async def run_loop(self) -> None:
        """Background loop: poll when bot_commands_enabled and token set."""
        while True:
            cfg = followup_store.load_config()
            if not cfg.bot_commands_enabled or not bot_token():
                self._polling = False
                await asyncio.sleep(5.0)
                continue
            self._polling = True
            try:
                await self._poll_once()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Follow-up bot poll error: %s", exc)
                await asyncio.sleep(3.0)

    async def _poll_once(self) -> None:
        url = bot_api_url("getUpdates")
        params = {
            "timeout": 25,
            "offset": self._offset,
            "allowed_updates": '["message"]',
        }
        async with httpx.AsyncClient(**TG_CLIENT_KW) as client:
            resp = await client.get(url, params=params, timeout=httpx.Timeout(35.0, connect=10.0))
        if resp.status_code != 200:
            await asyncio.sleep(2.0)
            return
        data = resp.json()
        if not data.get("ok"):
            await asyncio.sleep(2.0)
            return
        for upd in data.get("result") or []:
            self._offset = int(upd.get("update_id", 0)) + 1
            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip()
            if not text.startswith("/"):
                continue
            chat = msg.get("chat") or {}
            chat_id = str(chat.get("id") or "")
            if not chat_id:
                continue
            if not self._chat_allowed(chat_id):
                continue
            # Strip @botname
            cmd = text.split()[0].split("@")[0].lower()
            args = text.split()[1:]
            try:
                reply = await self._handle(cmd, args)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Follow-up bot command failed")
                reply = f"Ошибка: {exc}"
            try:
                await send_message(chat_id, reply)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Follow-up bot reply failed: %s", exc)

    def _chat_allowed(self, chat_id: str) -> bool:
        """Only configured watch/followup chats (or any if none set — first setup)."""
        cfg = followup_store.load_config()
        allowed = {
            resolve_chat_id(cfg.telegram_chat_id),
            resolve_chat_id(),
        }
        allowed = {c for c in allowed if c}
        if not allowed:
            return True
        return chat_id in allowed

    async def _handle(self, cmd: str, args: list[str]) -> str:
        from .followup import followup_runner

        if cmd in ("/start", "/help"):
            return _HELP

        if cmd == "/status":
            st = followup_runner.status()
            cfg = followup_store.load_config()
            return (
                f"<b>Follow-up status</b>\n"
                f"enabled: {'да' if cfg.enabled else 'нет'}\n"
                f"цикл: {'работает' if st.running else 'ожидание'}\n"
                f"watching: {st.wallets_watching} · done: {st.wallets_done}\n"
                f"last: {st.last_message or '—'}\n"
                f"алертов за цикл: {st.last_alerts_sent}\n"
                f"ошибка: {st.last_error or '—'}"
            )

        if cmd == "/wallets":
            rows = followup_store.list_wallets(status="watching", limit=30, include_deals=True)
            if not rows:
                return "Нет кошельков в watching."
            lines = [f"<b>Watching ({len(rows)})</b>"]
            for w in rows:
                short = f"{w.address[:6]}…{w.address[-4:]}"
                deals = ", ".join(
                    f"#{d.deal_index}@{_short_mcap(d.mcap_at_buy)}" for d in w.deals
                )
                lines.append(f"<code>{short}</code> deals={w.deal_count} [{deals or '—'}]")
            return "\n".join(lines)

        if cmd == "/filters":
            cfg = followup_store.load_config()
            return _format_filters(cfg)

        if cmd == "/on":
            cfg = followup_store.load_config()
            cfg = cfg.model_copy(update={"enabled": True})
            followup_store.save_config(cfg)
            followup_runner.notify_config_changed()
            return "Follow-up <b>включён</b>."

        if cmd == "/off":
            cfg = followup_store.load_config()
            cfg = cfg.model_copy(update={"enabled": False})
            followup_store.save_config(cfg)
            followup_runner.notify_config_changed()
            return "Follow-up <b>выключен</b>."

        if cmd == "/run":
            await followup_runner.run_now()
            return "Цикл Follow-up запрошен."

        if cmd == "/set_max_mcap":
            if not args:
                return "Использование: /set_max_mcap 15000"
            val = float(args[0].replace(",", "").replace("_", ""))
            cfg = followup_store.load_config()
            cfg = cfg.model_copy(update={"max_mcap_alert": val})
            followup_store.save_config(cfg)
            followup_runner.notify_config_changed()
            return f"max_mcap_alert = <b>{val:,.0f}</b>"

        if cmd == "/set_min_mcap":
            if not args:
                return "Использование: /set_min_mcap 1000 | /set_min_mcap off"
            raw = args[0].lower()
            if raw in ("off", "none", "-", "0"):
                val: float | None = None if raw != "0" else 0.0
                if raw == "0":
                    val = 0.0
                else:
                    val = None
            else:
                val = float(raw.replace(",", "").replace("_", ""))
            cfg = followup_store.load_config()
            cfg = cfg.model_copy(update={"min_mcap_alert": val})
            followup_store.save_config(cfg)
            followup_runner.notify_config_changed()
            return f"min_mcap_alert = <b>{val if val is not None else 'off'}</b>"

        if cmd == "/set_interval":
            if not args:
                return "Использование: /set_interval 300"
            sec = int(args[0])
            sec = max(60, min(sec, 86400))
            cfg = followup_store.load_config()
            cfg = cfg.model_copy(update={"interval_sec": sec})
            followup_store.save_config(cfg)
            followup_runner.notify_config_changed()
            return f"interval_sec = <b>{sec}</b>"

        return f"Неизвестная команда: {cmd}\n/help"


def _short_mcap(n: float | None) -> str:
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return f"{n:.0f}"


def _format_filters(cfg: FollowupConfig) -> str:
    deals = ",".join(str(x) for x in (cfg.alert_on_deals or [2, 3]))
    return (
        f"<b>Фильтры Follow-up</b>\n"
        f"max_mcap ≤ {cfg.max_mcap_alert:,.0f}\n"
        f"min_mcap ≥ {cfg.min_mcap_alert if cfg.min_mcap_alert is not None else 'off'}\n"
        f"bought_usd: {cfg.min_bought_usd or '—'} … {cfg.max_bought_usd or '—'}\n"
        f"alert_on_deals: [{deals}]\n"
        f"max_deals: {cfg.max_deals}\n"
        f"buys_only: {cfg.buys_only}\n"
        f"ingest_from_watch: {cfg.ingest_from_watch}\n"
        f"bot_commands: {cfg.bot_commands_enabled}\n"
        f"interval: {cfg.interval_sec}s"
    )


followup_bot = FollowupBot()
