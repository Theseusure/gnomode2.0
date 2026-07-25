# Gnomode — Robinhood Chain early buyers

Web app that takes one or more token addresses on **Robinhood Chain** (chain ID `4663`) and lists wallets that bought while market cap was still under a threshold (default **$15,000**).

## Stack

- **Backend:** Python 3.12+ / FastAPI / web3.py
- **Frontend:** Vite + React + TypeScript
- **Data:** public Robinhood RPC + DexScreener + Blockscout (no Alchemy)

## Quick start

```bash
# 1) Config
cp .env.example .env

# 2) Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
chmod +x scripts/*.sh
./scripts/dev-api.sh
# → http://127.0.0.1:8000  (API + health at /api/health)

# 3) Frontend (another terminal)
./scripts/dev-ui.sh
# → http://127.0.0.1:5173
```

Production-style single process (API serves `frontend/dist`):

```bash
cd frontend && npm install && npm run build && cd ..
source .venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

## Configuration (`.env`)

| Variable | Default | Notes |
|----------|---------|-------|
| `RPC_URL` | `https://rpc.mainnet.chain.robinhood.com` | Any EVM JSON-RPC |
| `BLOCKSCOUT_API_KEY` | empty | Optional Blockscout Pro key |
| `MCAP_THRESHOLD` | `15000` | USD |
| `LOG_CHUNK_SIZE` | `100000` | Block span per `eth_getLogs` batch |
| `RPC_CONCURRENCY` | `24` | Parallel RPC / batch size pressure |

## RPC upgrade path (when public RPC rate-limits)

1. **Public RPC** — free, fine for light use  
2. **[dRPC](https://drpc.org/)** — put your endpoint in `RPC_URL`  
3. **[QuickNode](https://www.quicknode.com/)** — archive-friendly `getLogs`  
4. **Blockscout Pro** — set `BLOCKSCOUT_API_KEY` for indexed transfers / metadata when RPC is throttled (fallback path)

Example:

```env
RPC_URL=https://YOUR_ENDPOINT.robinhood-mainnet.quiknode.pro/YOUR_TOKEN/
```

## How it works

1. Resolve Uniswap **V2 / V3 / V4** pools (DexScreener + on-chain factories for WETH/USDG).  
2. Stream `Swap` logs from pool birth; stop once mcap stays at/above the threshold.  
3. Resolve buyers via token `Transfer`s (PoolManager / routers → wallet).  
4. Replay price → `mcap = price_usd × totalSupply`.  
5. Keep wallets with at least one buy while `mcap < threshold`.  
6. Aggregate per wallet: tokens bought, USD≈, mcap at first buy, buy count.

Most Robinhood memecoins trade on **Uniswap V4** (pool id is a `bytes32`, not a pair address).

## API

- `POST /api/parse` `{ "tokens": ["0x…"], "mcap_threshold": 15000 }` → `{ "job_id": "…" }`  
- `GET /api/parse/{job_id}` — status, progress, results  
- `GET /api/health`

## Notes

- Early memecoins often trade on Uniswap V4 vs native ETH; V2/V3 are also supported.  
- If a token’s first on-chain price already implies mcap ≥ threshold, the result list is empty (correct).  
- Public RPC may be slow for long histories that never cross the threshold — use dRPC/QuickNode.  
- USD for ETH/WETH is derived from DexScreener (or CoinGecko fallback); USDG ≈ $1.
