"""FastAPI entrypoint for Robinhood early-buyer parser."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .jobs import jobs
from .models import (
    IndexStatus,
    JobResponse,
    ParseRequest,
    ScreenJobResponse,
    ScreenRequest,
    WatchConfig,
    WatchStatus,
)
from .screen_jobs import screen_jobs
from .token_index import token_index
from .gnome_banter import gnome_banter
from .watch import watch_runner
from .watch_store import watch_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title="Gnomode — Robinhood Early Buyers", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _start_background() -> None:
    from .gnome_lifecycle import install_death_hooks

    install_death_hooks()
    # Background: cold-build the 24h token index, then keep it fresh.
    asyncio.create_task(token_index.run_refresh_loop())
    asyncio.create_task(watch_runner.run_loop())
    asyncio.create_task(gnome_banter.run_loop())


@app.on_event("shutdown")
async def _shutdown_announce() -> None:
    from .gnome_lifecycle import announce_death

    announce_death("остановка сервера (shutdown)")


@app.get("/api/index/status", response_model=IndexStatus)
async def index_status():
    return IndexStatus(**token_index.status())


@app.post("/api/index/refresh", response_model=IndexStatus)
async def index_refresh():
    # Fire-and-forget incremental refresh (no-op if one is already running).
    asyncio.create_task(token_index.refresh(full=False))
    return IndexStatus(**token_index.status())


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "chain_id": 4663,
        "rpc_url": settings.rpc_url.split("/v2/")[0] if "/v2/" in settings.rpc_url else settings.rpc_url,
        "mcap_threshold": settings.mcap_threshold,
    }


@app.post("/api/parse", response_model=JobResponse)
async def start_parse(req: ParseRequest):
    tokens = []
    for raw in req.tokens:
        for part in raw.replace(";", "\n").replace(",", "\n").split():
            part = part.strip()
            if part:
                tokens.append(part)
    if not tokens:
        raise HTTPException(400, "Provide at least one token address")
    # Dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tokens:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    req.tokens = uniq
    return await jobs.create(req)


@app.get("/api/parse/{job_id}", response_model=JobResponse)
async def get_parse(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/screen", response_model=ScreenJobResponse)
async def start_screen(req: ScreenRequest):
    return await screen_jobs.create(req)


@app.get("/api/screen/{job_id}", response_model=ScreenJobResponse)
async def get_screen(job_id: str):
    job = screen_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/watch", response_model=WatchConfig)
async def get_watch():
    return watch_store.load_config()


@app.put("/api/watch", response_model=WatchConfig)
async def put_watch(cfg: WatchConfig):
    saved = watch_store.save_config(cfg)
    watch_runner.notify_config_changed()
    return saved


@app.get("/api/watch/status", response_model=WatchStatus)
async def get_watch_status():
    st = watch_runner.status()
    bits = gnome_banter.status_bits()
    return st.model_copy(update=bits)


@app.post("/api/watch/run", response_model=WatchStatus)
async def watch_run_now():
    return await watch_runner.run_now()


@app.post("/api/watch/stop", response_model=WatchStatus)
async def watch_stop():
    return await watch_runner.stop()


@app.post("/api/watch/reset-counters", response_model=WatchStatus)
async def watch_reset_counters():
    return watch_runner.reset_counters()


@app.post("/api/watch/test-telegram")
async def watch_test_telegram():
    from .telegram import test_telegram_connection

    cfg = watch_store.load_config()
    try:
        result = await test_telegram_connection(
            chat_id=cfg.telegram_chat_id,
            topic_id=cfg.telegram_topic_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    watch_runner._append_log("telegram", result.get("message") or "Telegram OK")
    return result


@app.post("/api/watch/clear-seen")
async def watch_clear_seen():
    watch_store.clear_seen()
    return {"ok": True, "seen_count": 0}


# Serve built frontend if present
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        index = _frontend_dist / "index.html"
        file_path = _frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(index)
