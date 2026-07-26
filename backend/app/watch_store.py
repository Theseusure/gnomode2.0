"""Persistent watch config, seen-set, and last-success timestamp (JSON on disk)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from .config import settings
from .models import WatchConfig

logger = logging.getLogger(__name__)

# Cap seen keys so the file cannot grow without bound.
_SEEN_MAX = 50_000
_MAX_CATCHUP_HOURS = 24.0


def seen_key(wallet: str, token: str) -> str:
    return f"{wallet.strip().lower()}:{token.strip().lower()}"


def catchup_lookback_hours(last_success_ts: float | None, *, now: float | None = None) -> float:
    """Hours of token age to cover since last successful watch run.

    Never ran, or gap ≥ 24h → 24h. Otherwise the exact downtime gap.
    """
    import time

    now_ts = time.time() if now is None else now
    if last_success_ts is None or last_success_ts <= 0:
        return _MAX_CATCHUP_HOURS
    gap_h = (now_ts - last_success_ts) / 3600.0
    if gap_h >= _MAX_CATCHUP_HOURS:
        return _MAX_CATCHUP_HOURS
    # Tiny floor so a near-instant re-enable still has a non-zero window.
    return max(gap_h, 1.0 / 60.0)


class WatchStore:
    def __init__(
        self,
        config_path: str | Path | None = None,
        seen_path: str | Path | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        self._config_path = Path(config_path or settings.watch_config_path)
        self._seen_path = Path(seen_path or settings.watch_seen_path)
        self._state_path = Path(state_path or settings.watch_state_path)
        self._lock = threading.Lock()
        self._seen: set[str] | None = None
        self._last_success_ts: float | None | object = _UNSET

    def load_config(self) -> WatchConfig:
        with self._lock:
            if not self._config_path.is_file():
                return WatchConfig()
            try:
                raw = json.loads(self._config_path.read_text(encoding="utf-8"))
                return WatchConfig.model_validate(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load watch config %s: %r", self._config_path, exc)
                return WatchConfig()

    def save_config(self, cfg: WatchConfig) -> WatchConfig:
        with self._lock:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
            payload = cfg.model_dump(mode="json")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(self._config_path)
            return cfg

    def _ensure_seen_loaded(self) -> set[str]:
        if self._seen is not None:
            return self._seen
        seen: set[str] = set()
        if self._seen_path.is_file():
            try:
                raw = json.loads(self._seen_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    seen = {str(x).lower() for x in raw if x}
                elif isinstance(raw, dict) and isinstance(raw.get("keys"), list):
                    seen = {str(x).lower() for x in raw["keys"] if x}
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load watch seen %s: %r", self._seen_path, exc)
        self._seen = seen
        return seen

    def _persist_seen(self) -> None:
        assert self._seen is not None
        keys = list(self._seen)
        if len(keys) > _SEEN_MAX:
            keys = keys[-_SEEN_MAX:]
            self._seen = set(keys)
        self._seen_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._seen_path.with_suffix(self._seen_path.suffix + ".tmp")
        tmp.write_text(json.dumps({"keys": keys}, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self._seen_path)

    def load_seen(self) -> set[str]:
        with self._lock:
            return set(self._ensure_seen_loaded())

    def is_seen(self, wallet: str, token: str) -> bool:
        with self._lock:
            return seen_key(wallet, token) in self._ensure_seen_loaded()

    def mark_seen(self, pairs: list[tuple[str, str]]) -> int:
        """Mark wallet+token pairs as seen. Returns number of newly added keys."""
        if not pairs:
            return 0
        with self._lock:
            seen = self._ensure_seen_loaded()
            before = len(seen)
            for wallet, token in pairs:
                seen.add(seen_key(wallet, token))
            added = len(seen) - before
            if added:
                self._persist_seen()
            return added

    def clear_seen(self) -> None:
        with self._lock:
            self._seen = set()
            self._persist_seen()

    def seen_count(self) -> int:
        with self._lock:
            return len(self._ensure_seen_loaded())

    def _ensure_state_loaded(self) -> float | None:
        if self._last_success_ts is not _UNSET:
            return self._last_success_ts  # type: ignore[return-value]
        ts: float | None = None
        if self._state_path.is_file():
            try:
                raw = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    val = raw.get("last_success_ts")
                    if isinstance(val, (int, float)) and val > 0:
                        ts = float(val)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load watch state %s: %r", self._state_path, exc)
        self._last_success_ts = ts
        return ts

    def load_last_success_ts(self) -> float | None:
        with self._lock:
            return self._ensure_state_loaded()

    def save_last_success_ts(self, ts: float) -> None:
        with self._lock:
            self._last_success_ts = float(ts)
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            payload = {"last_success_ts": self._last_success_ts}
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self._state_path)


_UNSET = object()

watch_store = WatchStore()
