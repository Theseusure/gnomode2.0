"""Хвать: one-trade early buyers → follow-up alerts at low mcap."""

from __future__ import annotations

from typing import Any

from .followup import followup_runner
from .followup_store import followup_store
from .models import (
    FollowupConfig,
    TokensUniquePeriod,
    WatchConfig,
    WatchScreenFilters,
    WatchWalletFilters,
)
from .watch import watch_runner
from .watch_store import watch_store

# First buy and subsequent-alert mcap caps (USD).
HVAT_MCAP = 20_000.0


def apply_hvat_profile(*, enable: bool = True) -> dict[str, Any]:
    """Enable autoparse + follow-up; keep existing screen/wallet filters."""
    wcfg = watch_store.load_config()
    wallet = wcfg.wallet.model_dump()
    if wallet.get("mcap_threshold") is None:
        wallet["mcap_threshold"] = HVAT_MCAP
    if wallet.get("min_tokens_traded_7d") is None and wallet.get("max_tokens_traded_7d") is None:
        wallet["min_tokens_traded_7d"] = 1.0
        wallet["max_tokens_traded_7d"] = 1.0
    if not wallet.get("tokens_unique_period"):
        wallet["tokens_unique_period"] = TokensUniquePeriod.d7.value
    wallet["exclude_honeypots"] = True if wallet.get("exclude_honeypots") is None else wallet["exclude_honeypots"]

    wcfg = WatchConfig.model_validate(
        {
            **wcfg.model_dump(),
            "enabled": enable,
            "wallet": wallet,
        }
    )
    watch_store.save_config(wcfg)
    watch_runner.notify_config_changed()

    fcfg = followup_store.load_config()
    alert_mcap = float(wallet.get("mcap_threshold") or HVAT_MCAP)
    fcfg = FollowupConfig.model_validate(
        {
            **fcfg.model_dump(),
            "enabled": enable,
            "max_mcap_alert": alert_mcap,
            "alert_on_deals": [2, 3],
            "max_deals": 3,
            "buys_only": True,
            "ingest_from_watch": True,
        }
    )
    followup_store.save_config(fcfg)
    followup_runner.notify_config_changed()

    return {
        "ok": True,
        "mcap_cap": alert_mcap,
        "watch": wcfg,
        "followup": fcfg,
    }


def save_hvat_filters(
    *,
    screen: WatchScreenFilters | dict[str, Any],
    wallet: WatchWalletFilters | dict[str, Any],
    max_tokens_per_cycle: int | None = None,
    sync_followup_mcap: bool = True,
) -> dict[str, Any]:
    """Persist token/wallet filters used by Хвать (via watch config)."""
    wcfg = watch_store.load_config()
    screen_model = (
        screen
        if isinstance(screen, WatchScreenFilters)
        else WatchScreenFilters.model_validate(screen)
    )
    wallet_model = (
        wallet
        if isinstance(wallet, WatchWalletFilters)
        else WatchWalletFilters.model_validate(wallet)
    )
    payload: dict[str, Any] = {
        **wcfg.model_dump(),
        "screen": screen_model.model_dump(),
        "wallet": wallet_model.model_dump(),
    }
    if max_tokens_per_cycle is not None:
        payload["max_tokens_per_cycle"] = int(max_tokens_per_cycle)
    saved = watch_store.save_config(WatchConfig.model_validate(payload))
    watch_runner.notify_config_changed()

    fcfg = followup_store.load_config()
    if sync_followup_mcap and wallet_model.mcap_threshold is not None:
        fcfg = FollowupConfig.model_validate(
            {
                **fcfg.model_dump(),
                "max_mcap_alert": float(wallet_model.mcap_threshold),
            }
        )
        followup_store.save_config(fcfg)
        followup_runner.notify_config_changed()

    return {"ok": True, "watch": saved, "followup": fcfg}


def hvat_status() -> dict[str, Any]:
    w = watch_runner.status()
    f = followup_runner.status()
    cfg = watch_store.load_config()
    return {
        "mcap_cap": float(cfg.wallet.mcap_threshold or HVAT_MCAP),
        "watch": w,
        "followup": f,
        "config": cfg,
        "profile": {
            "one_trade": True,
            "max_tokens_traded_7d": cfg.wallet.max_tokens_traded_7d,
            "min_tokens_traded_7d": cfg.wallet.min_tokens_traded_7d,
            "tokens_unique_period": cfg.wallet.tokens_unique_period,
            "first_buy_max_mcap": cfg.wallet.mcap_threshold,
            "alert_deals": [2, 3],
            "alert_max_mcap": followup_store.load_config().max_mcap_alert,
        },
    }
