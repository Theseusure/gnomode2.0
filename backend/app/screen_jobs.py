"""In-memory screen job store."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from .models import JobProgress, JobStatus, ScreenJobResponse, ScreenRequest, ScreenedToken
from .screener import screen_tokens

logger = logging.getLogger(__name__)


class ScreenJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ScreenJobResponse] = {}
        self._lock = asyncio.Lock()

    def get(self, job_id: str) -> ScreenJobResponse | None:
        return self._jobs.get(job_id)

    async def create(self, req: ScreenRequest) -> ScreenJobResponse:
        job_id = uuid.uuid4().hex[:12]
        job = ScreenJobResponse(
            job_id=job_id,
            status=JobStatus.queued,
            progress=JobProgress(stage="queued", message="Queued", percent=0),
        )
        self._jobs[job_id] = job
        asyncio.create_task(self._run(job_id, req))
        return job

    async def _update(self, job_id: str, **kwargs: Any) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            for k, v in kwargs.items():
                if k == "progress" and isinstance(v, JobProgress):
                    job.progress = v
                elif hasattr(job, k):
                    setattr(job, k, v)

    async def _run(self, job_id: str, req: ScreenRequest) -> None:
        await self._update(
            job_id,
            status=JobStatus.running,
            progress=JobProgress(stage="running", message="Starting…", percent=0.01),
        )

        async def on_progress(stage: str, message: str, percent: float) -> None:
            await self._update(
                job_id,
                progress=JobProgress(
                    stage=stage,
                    message=message,
                    percent=round(percent * 100, 2),
                ),
            )

        async def on_tokens(tokens: list[ScreenedToken]) -> None:
            await self._update(job_id, results=list(tokens))

        try:
            tokens = await screen_tokens(
                req, on_progress=on_progress, on_tokens=on_tokens
            )
            await self._update(
                job_id,
                status=JobStatus.done,
                results=tokens,
                progress=JobProgress(
                    stage="done",
                    message=f"Done — {len(tokens)} tokens",
                    percent=100,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Screen job %s failed", job_id)
            await self._update(
                job_id,
                status=JobStatus.error,
                error=str(exc),
                progress=JobProgress(stage="error", message=str(exc), percent=100),
            )


screen_jobs = ScreenJobStore()
