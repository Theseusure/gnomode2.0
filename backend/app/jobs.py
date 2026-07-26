"""In-memory parse job store."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from .chain import RpcClient
from .config import settings
from .models import (
    JobLogEntry,
    JobProgress,
    JobResponse,
    JobStatus,
    ParseRequest,
    TokenParseResult,
)
from .replay import parse_token

logger = logging.getLogger(__name__)

_LOG_MAX = 250


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobResponse] = {}
        self._lock = asyncio.Lock()

    def get(self, job_id: str) -> JobResponse | None:
        return self._jobs.get(job_id)

    def has_active(self) -> bool:
        """True if any parse job is queued or running (used to yield resources)."""
        return any(
            j.status in (JobStatus.queued, JobStatus.running)
            for j in self._jobs.values()
        )

    async def create(self, req: ParseRequest) -> JobResponse:
        job_id = uuid.uuid4().hex[:12]
        job = JobResponse(
            job_id=job_id,
            status=JobStatus.queued,
            progress=JobProgress(stage="queued", message="Queued", percent=0),
            log=[
                JobLogEntry(
                    ts=time.time(),
                    stage="queued",
                    message=f"Queued — {len([t for t in req.tokens if t.strip()])} token(s)",
                    percent=0,
                )
            ],
        )
        self._jobs[job_id] = job
        asyncio.create_task(self._run(job_id, req))
        return job

    def _append_log(self, job: JobResponse, progress: JobProgress) -> None:
        entry = JobLogEntry(
            ts=time.time(),
            stage=progress.stage,
            message=progress.message,
            percent=progress.percent,
            token=progress.current_token,
        )
        if job.log:
            last = job.log[-1]
            # Same step text: refresh percent/ts instead of flooding the UI.
            if last.stage == entry.stage and last.message == entry.message:
                job.log[-1] = entry
                return
        job.log.append(entry)
        if len(job.log) > _LOG_MAX:
            job.log = job.log[-_LOG_MAX:]

    async def _update(self, job_id: str, **kwargs: Any) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            for k, v in kwargs.items():
                if k == "progress" and isinstance(v, JobProgress):
                    job.progress = v
                    self._append_log(job, v)
                elif hasattr(job, k):
                    setattr(job, k, v)

    async def _run(self, job_id: str, req: ParseRequest) -> None:
        threshold = (
            req.mcap_threshold
            if req.mcap_threshold is not None
            else settings.mcap_threshold
        )
        await self._update(
            job_id,
            status=JobStatus.running,
            progress=JobProgress(stage="running", message="Starting…", percent=0.01),
        )
        rpc = RpcClient()
        results: list[TokenParseResult] = []
        tokens = [t.strip() for t in req.tokens if t.strip()]
        n = max(len(tokens), 1)

        try:
            for i, token in enumerate(tokens):
                base = i / n
                span = 1.0 / n
                await self._update(
                    job_id,
                    progress=JobProgress(
                        stage="token",
                        message=f"Token {i + 1}/{n}: {token[:10]}…",
                        percent=round(base * 100, 2),
                        current_token=token,
                    ),
                )

                async def on_progress(
                    stage: str,
                    message: str,
                    percent: float,
                    _i=i,
                    _base=base,
                    _span=span,
                    _token=token,
                ):
                    await self._update(
                        job_id,
                        progress=JobProgress(
                            stage=stage,
                            message=message,
                            percent=round((_base + percent * _span) * 100, 2),
                            current_token=_token,
                        ),
                    )

                try:
                    result = await parse_token(
                        rpc,
                        token,
                        threshold,
                        on_progress=on_progress,
                        exclude_honeypots=req.exclude_honeypots,
                        wallet_filters=req,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed parsing %s", token)
                    result = TokenParseResult(token=token, error=str(exc))
                    await on_progress("error", f"Token failed: {exc}", 1.0)
                results.append(result)
                await self._update(job_id, results=list(results))

            total_wallets = sum(len(r.buyers) for r in results)
            await self._update(
                job_id,
                status=JobStatus.done,
                results=results,
                progress=JobProgress(
                    stage="done",
                    message=f"Done — {total_wallets} wallets across {len(results)} token(s)",
                    percent=100,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job_id)
            await self._update(
                job_id,
                status=JobStatus.error,
                error=str(exc),
                progress=JobProgress(stage="error", message=str(exc), percent=100),
            )


jobs = JobStore()
