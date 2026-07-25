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
from .models import IndexStatus, JobResponse, ParseRequest, ScreenJobResponse, ScreenRequest
from .screen_jobs import screen_jobs
from .token_index import token_index

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
async def _start_token_index() -> None:
    # Background: cold-build the 24h token index, then keep it fresh.
    asyncio.create_task(token_index.run_refresh_loop())


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
