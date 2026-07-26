"""Application settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    rpc_url: str = "https://rpc.mainnet.chain.robinhood.com"
    blockscout_api_key: str = ""
    mcap_threshold: float = 15_000.0
    # Larger chunks = fewer round-trips (filtered getLogs stay small)
    log_chunk_size: int = 100_000
    # Public Robinhood RPC rate-limits aggressively; keep this low.
    rpc_concurrency: int = 6
    # Funded EOА used as eth_call `from` for honeypot buy→sell simulation
    honeypot_sim_whale: str = ""
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
