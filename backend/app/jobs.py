"""In-memory parse job store."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from .chain import RpcClient
from .config import settings
from .models import JobProgress, JobResponse, JobStatus, ParseRequest, TokenParseResult
from .replay import parse_token

logger = logging.getLogger(__name__)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobResponse] = {}
        self._lock = asyncio.Lock()

    def get(self, job_id: str) -> JobResponse | None:
        return self._jobs.get(job_id)

    async def create(self, req: ParseRequest) -> JobResponse:
        job_id = uuid.uuid4().hex[:12]
        job = JobResponse(
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

                async def on_progress(stage: str, message: str, percent: float, _i=i, _base=base, _span=span, _token=token):
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
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed parsing %s", token)
                    result = TokenParseResult(token=token, error=str(exc))
                results.append(result)
                await self._update(job_id, results=list(results))

            await self._update(
                job_id,
                status=JobStatus.done,
                results=results,
                progress=JobProgress(
                    stage="done",
                    message=f"Done — {sum(len(r.buyers) for r in results)} wallets",
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
