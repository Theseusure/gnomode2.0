"""Tests for gnome start/death Telegram helpers (no real network)."""

from __future__ import annotations

import asyncio

from app.gnome_lifecycle import announce_death, announce_work_start
from app.models import WatchConfig
from app.watch_store import WatchStore


def test_announce_work_and_death(tmp_path, monkeypatch):
    store = WatchStore(
        config_path=tmp_path / "watch.json",
        seen_path=tmp_path / "seen.json",
        state_path=tmp_path / "state.json",
    )
    store.save_config(
        WatchConfig(enabled=True, telegram_chat_id="99", telegram_topic_id="3")
    )

    import app.gnome_lifecycle as life
    import app.config as cfg_mod

    monkeypatch.setattr(life, "watch_store", store)
    monkeypatch.setattr(cfg_mod.settings, "telegram_bot_token", "tok")
    monkeypatch.setattr(cfg_mod.settings, "telegram_chat_id", "99")

    sent: list[dict] = []

    async def fake_send(chat_id, text, *, topic_id=None):
        sent.append({"chat_id": chat_id, "text": text, "topic_id": topic_id})

    def fake_send_sync(chat_id, text, *, topic_id=None):
        sent.append({"chat_id": chat_id, "text": text, "topic_id": topic_id, "sync": True})

    monkeypatch.setattr(life, "send_message", fake_send)
    monkeypatch.setattr(life, "send_message_sync", fake_send_sync)
    # reset death flag
    life._death_announced = False

    asyncio.run(announce_work_start())
    assert sent and "За работу!" in sent[0]["text"]
    assert sent[0]["topic_id"] == 3

    announce_death("тест падения")
    assert any("гном умер по причине" in s["text"] and "тест падения" in s["text"] for s in sent)

    n = len(sent)
    announce_death("второй раз")
    assert len(sent) == n  # deduped
