"""SQLite store for follow-up wallets (WAL, durable, lightweight)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .config import settings
from .models import (
    BuyerRow,
    FollowupConfig,
    FollowupDealRow,
    FollowupWalletRow,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    address TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'watching',
    deal_count INTEGER NOT NULL DEFAULT 0,
    wallet_balance_eth REAL,
    tokens_traded_7d INTEGER,
    raybot_synced INTEGER NOT NULL DEFAULT 0,
    first_token TEXT NOT NULL DEFAULT '',
    first_mcap REAL,
    discovered_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deals (
    wallet TEXT NOT NULL,
    token TEXT NOT NULL,
    token_symbol TEXT NOT NULL DEFAULT '',
    deal_index INTEGER NOT NULL,
    mcap_at_buy REAL,
    bought_usd REAL,
    tx_hash TEXT NOT NULL DEFAULT '',
    notified INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    PRIMARY KEY (wallet, token)
);
CREATE INDEX IF NOT EXISTS idx_deals_wallet ON deals(wallet);
CREATE INDEX IF NOT EXISTS idx_wallets_status ON wallets(status);
CREATE TABLE IF NOT EXISTS alert_log (
    wallet TEXT NOT NULL,
    token TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (wallet, token, kind)
);
"""


class FollowupStore:
    def __init__(
        self,
        db_path: str | None = None,
        config_path: str | None = None,
    ) -> None:
        self._db_path = Path(db_path or settings.followup_db_path)
        self._config_path = Path(config_path or settings.followup_config_path)
        self._lock = threading.Lock()
        self._ensured = False

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure(self) -> None:
        if self._ensured:
            return
        with self._lock:
            if self._ensured:
                return
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
                conn.commit()
            self._ensured = True

    # --- config (JSON, same atomic pattern as watch) ---

    def load_config(self) -> FollowupConfig:
        path = self._config_path
        if not path.is_file():
            return FollowupConfig()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return FollowupConfig.model_validate(data)
        except Exception:  # noqa: BLE001
            return FollowupConfig()

    def save_config(self, cfg: FollowupConfig) -> FollowupConfig:
        path = self._config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            cfg.model_dump_json(indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        return cfg

    # --- wallets / deals ---

    def ingest_buyers(
        self,
        buyers: list[BuyerRow],
        *,
        max_deals: int = 3,
        max_mcap_alert: float | None = None,
    ) -> list[FollowupDealRow]:
        """Insert deals for early buyers (skip if wallet+token exists).

        Returns newly inserted deal rows (for RayBot sync + optional alerts).
        """
        self._ensure()
        now = time.time()
        inserted: list[FollowupDealRow] = []
        with self._lock:
            with self._connect() as conn:
                for b in buyers:
                    wallet = b.wallet.lower()
                    token = b.token.lower()
                    if max_mcap_alert is not None and b.mcap_at_first_buy > max_mcap_alert:
                        continue
                    existing = conn.execute(
                        "SELECT 1 FROM deals WHERE wallet=? AND token=?",
                        (wallet, token),
                    ).fetchone()
                    if existing:
                        continue
                    wrow = conn.execute(
                        "SELECT deal_count, status FROM wallets WHERE address=?",
                        (wallet,),
                    ).fetchone()
                    if wrow is None:
                        conn.execute(
                            "INSERT INTO wallets ("
                            "address, status, deal_count, wallet_balance_eth, "
                            "tokens_traded_7d, raybot_synced, first_token, first_mcap, "
                            "discovered_at, updated_at"
                            ") VALUES (?, 'watching', 1, ?, ?, 0, ?, ?, ?, ?)",
                            (
                                wallet,
                                b.wallet_balance_eth,
                                b.tokens_traded_7d,
                                token,
                                b.mcap_at_first_buy,
                                now,
                                now,
                            ),
                        )
                        deal_index = 1
                    else:
                        if wrow["status"] == "done":
                            continue
                        deal_index = int(wrow["deal_count"]) + 1
                        if deal_index > max_deals:
                            continue
                        conn.execute(
                            "UPDATE wallets SET deal_count=?, updated_at=?, "
                            "wallet_balance_eth=COALESCE(?, wallet_balance_eth), "
                            "tokens_traded_7d=COALESCE(?, tokens_traded_7d) "
                            "WHERE address=?",
                            (
                                deal_index,
                                now,
                                b.wallet_balance_eth,
                                b.tokens_traded_7d,
                                wallet,
                            ),
                        )
                    conn.execute(
                        "INSERT INTO deals ("
                        "wallet, token, token_symbol, deal_index, mcap_at_buy, "
                        "bought_usd, tx_hash, notified, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                        (
                            wallet,
                            token,
                            b.token_symbol or "",
                            deal_index,
                            b.mcap_at_first_buy,
                            b.bought_usd,
                            b.first_tx or "",
                            now,
                        ),
                    )
                    if deal_index >= max_deals:
                        conn.execute(
                            "UPDATE wallets SET status='done', updated_at=? WHERE address=?",
                            (now, wallet),
                        )
                    inserted.append(
                        FollowupDealRow(
                            wallet=wallet,
                            token=token,
                            token_symbol=b.token_symbol or "",
                            deal_index=deal_index,
                            mcap_at_buy=b.mcap_at_first_buy,
                            bought_usd=b.bought_usd,
                            tx_hash=b.first_tx or "",
                            notified=False,
                            created_at=now,
                        )
                    )
                conn.commit()
        return inserted

    def record_deal(
        self,
        *,
        wallet: str,
        token: str,
        token_symbol: str = "",
        mcap_at_buy: float | None,
        bought_usd: float | None = None,
        tx_hash: str = "",
        max_deals: int = 3,
    ) -> FollowupDealRow | None:
        """Record a new distinct-token deal. Returns row if inserted, else None."""
        self._ensure()
        wallet_l = wallet.lower()
        token_l = token.lower()
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                if conn.execute(
                    "SELECT 1 FROM deals WHERE wallet=? AND token=?",
                    (wallet_l, token_l),
                ).fetchone():
                    return None
                wrow = conn.execute(
                    "SELECT deal_count, status FROM wallets WHERE address=?",
                    (wallet_l,),
                ).fetchone()
                if wrow is None:
                    return None
                if wrow["status"] != "watching":
                    return None
                deal_index = int(wrow["deal_count"]) + 1
                if deal_index > max_deals:
                    return None
                conn.execute(
                    "INSERT INTO deals ("
                    "wallet, token, token_symbol, deal_index, mcap_at_buy, "
                    "bought_usd, tx_hash, notified, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                    (
                        wallet_l,
                        token_l,
                        token_symbol,
                        deal_index,
                        mcap_at_buy,
                        bought_usd,
                        tx_hash,
                        now,
                    ),
                )
                status = "done" if deal_index >= max_deals else "watching"
                conn.execute(
                    "UPDATE wallets SET deal_count=?, status=?, updated_at=? WHERE address=?",
                    (deal_index, status, now, wallet_l),
                )
                conn.commit()
                return FollowupDealRow(
                    wallet=wallet_l,
                    token=token_l,
                    token_symbol=token_symbol,
                    deal_index=deal_index,
                    mcap_at_buy=mcap_at_buy,
                    bought_usd=bought_usd,
                    tx_hash=tx_hash,
                    notified=False,
                    created_at=now,
                )

    def mark_notified(self, wallet: str, token: str, kind: str = "deal") -> bool:
        self._ensure()
        wallet_l = wallet.lower()
        token_l = token.lower()
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                try:
                    conn.execute(
                        "INSERT INTO alert_log (wallet, token, kind, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (wallet_l, token_l, kind, now),
                    )
                except sqlite3.IntegrityError:
                    return False
                conn.execute(
                    "UPDATE deals SET notified=1 WHERE wallet=? AND token=?",
                    (wallet_l, token_l),
                )
                conn.commit()
                return True

    def mark_raybot_synced(self, addresses: list[str], synced: bool = True) -> None:
        if not addresses:
            return
        self._ensure()
        flag = 1 if synced else 0
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                for addr in addresses:
                    conn.execute(
                        "UPDATE wallets SET raybot_synced=?, updated_at=? WHERE address=?",
                        (flag, now, addr.lower()),
                    )
                conn.commit()

    def list_watching(self) -> list[str]:
        self._ensure()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT address FROM wallets WHERE status='watching' ORDER BY discovered_at"
            ).fetchall()
        return [r["address"] for r in rows]

    def known_tokens(self, wallet: str) -> set[str]:
        self._ensure()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT token FROM deals WHERE wallet=?",
                (wallet.lower(),),
            ).fetchall()
        return {r["token"] for r in rows}

    def counts(self) -> tuple[int, int]:
        self._ensure()
        with self._connect() as conn:
            watching = conn.execute(
                "SELECT COUNT(*) AS c FROM wallets WHERE status='watching'"
            ).fetchone()["c"]
            done = conn.execute(
                "SELECT COUNT(*) AS c FROM wallets WHERE status='done'"
            ).fetchone()["c"]
        return int(watching), int(done)

    def list_wallets(
        self,
        *,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
        include_deals: bool = True,
    ) -> list[FollowupWalletRow]:
        self._ensure()
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM wallets WHERE status=? "
                    "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM wallets ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            out: list[FollowupWalletRow] = []
            for r in rows:
                deals: list[FollowupDealRow] = []
                if include_deals:
                    drows = conn.execute(
                        "SELECT * FROM deals WHERE wallet=? ORDER BY deal_index",
                        (r["address"],),
                    ).fetchall()
                    deals = [
                        FollowupDealRow(
                            wallet=d["wallet"],
                            token=d["token"],
                            token_symbol=d["token_symbol"] or "",
                            deal_index=int(d["deal_index"]),
                            mcap_at_buy=d["mcap_at_buy"],
                            bought_usd=d["bought_usd"],
                            tx_hash=d["tx_hash"] or "",
                            notified=bool(d["notified"]),
                            created_at=float(d["created_at"]),
                        )
                        for d in drows
                    ]
                out.append(
                    FollowupWalletRow(
                        address=r["address"],
                        status=r["status"],
                        deal_count=int(r["deal_count"]),
                        wallet_balance_eth=r["wallet_balance_eth"],
                        tokens_traded_7d=r["tokens_traded_7d"],
                        raybot_synced=bool(r["raybot_synced"]),
                        first_token=r["first_token"] or "",
                        first_mcap=r["first_mcap"],
                        discovered_at=float(r["discovered_at"]),
                        updated_at=float(r["updated_at"]),
                        deals=deals,
                    )
                )
        return out


followup_store = FollowupStore()
