"""Хвать: one-trade early buyers → follow-up alerts at low mcap."""

from __future__ import annotations

from typing import Any

from .followup import followup_runner
from .followup_store import followup_store
from .models import FollowupConfig, WatchConfig
from .watch import watch_runner
from .watch_store import watch_store

# First buy and subsequent-alert mcap caps (USD).
HVAT_MCAP = 20_000.0


def apply_hvat_profile(*, enable: bool = True) -> dict[str, Any]:
    """Enable autoparse + follow-up with Хвать defaults (1 trade, mcap ≤ 20k)."""
    wcfg = watch_store.load_config()
    wcfg = WatchConfig.model_validate(
        {
            **wcfg.model_dump(),
            "enabled": enable,
            "wallet": {
                **wcfg.wallet.model_dump(),
                "mcap_threshold": HVAT_MCAP,
                "min_tokens_traded_7d": 1.0,
                "max_tokens_traded_7d": 1.0,
                "exclude_honeypots": True,
            },
        }
    )
    watch_store.save_config(wcfg)
    watch_runner.notify_config_changed()

    fcfg = followup_store.load_config()
    fcfg = FollowupConfig.model_validate(
        {
            **fcfg.model_dump(),
            "enabled": enable,
            "max_mcap_alert": HVAT_MCAP,
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
        "mcap_cap": HVAT_MCAP,
        "watch": wcfg,
        "followup": fcfg,
    }


def hvat_status() -> dict[str, Any]:
    w = watch_runner.status()
    f = followup_runner.status()
    return {
        "mcap_cap": HVAT_MCAP,
        "watch": w,
        "followup": f,
        "profile": {
            "one_trade": True,
            "max_tokens_traded_7d": 1,
            "first_buy_max_mcap": HVAT_MCAP,
            "alert_deals": [2, 3],
            "alert_max_mcap": HVAT_MCAP,
        },
    }
