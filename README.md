# Gnomode — сканер токенов Robinhood Chain

Веб-приложение для анализа токенов на **Robinhood Chain** (chain ID `4663`). Две основные функции:

1. **Screener** — отбор токенов по фильтрам в духе DexScreener (ликвидность, возраст пары, трейдеры, market cap).
2. **Early buyers** — поиск кошельков, которые купили токен, пока market cap был ниже порога (по умолчанию **$15 000**).

---

## Возможности

### Screener

- Сканирует каталог ERC-20 через Blockscout.
- Обогащает метрики через DexScreener (`/tokens/v1/robinhood/...`).
- Для каждого токена выбирает лучшую Robinhood-пару (по ликвидности).
- Отсекает honeypot через **GMGN token security** (тот же источник, что на gmgn.ai):
  `is_honeypot` / высокий buy·sell tax. Если GMGN не знает вердикт — лёгкий fallback
  по DexScreener (нет продаж при покупках). Быстро: десятки токенов за несколько секунд.
- Локальные фильтры (min/max, пустое поле = без ограничения):
  - **liquidity** — `liquidity.usd`
  - **pair age** — возраст пары в часах от `pairCreatedAt`
  - **traders** — `txns.h24.buys + sells` (прокси числа транзакций, не уникальные кошельки)
  - **mcap** — `marketCap`, иначе `fdv`
- Сортировка: liquidity / market_cap / traders / pair_age.
- Результаты можно экспортировать в CSV.
- Выбранные токены можно перенести во вкладку **Early buyers**.
- Состояние вкладок сохраняется при переключении (таблица не сбрасывается).

### Early buyers

- Принимает один или несколько адресов токенов.
- Перед тяжёлым replay проверяет honeypot через GMGN (можно отключить в UI).
- Находит пулы Uniswap **V2 / V3 / V4** (DexScreener + on-chain factories для WETH/USDG).
- Проигрывает историю свопов до пересечения порога mcap.
- Собирает EOA-покупателей: объём в токенах, USD≈, mcap на первой покупке, число покупок.
- Экспорт в CSV, ссылки на GMGN и Blockscout.

---

## Стек

| Слой | Технологии |
|------|------------|
| Backend | Python 3.12+, FastAPI, web3.py, httpx, Pydantic |
| Frontend | Vite, React 19, TypeScript |
| Данные | публичный Robinhood RPC, DexScreener, Blockscout (без Alchemy) |

---

## Быстрый старт

### 1. Конфиг

```bash
cp .env.example .env
# при необходимости отредактируйте .env
```

### 2. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
chmod +x scripts/*.sh
./scripts/dev-api.sh
```

API: [http://127.0.0.1:8000](http://127.0.0.1:8000)  
Health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### 3. Frontend (второй терминал)

```bash
./scripts/dev-ui.sh
```

UI: [http://127.0.0.1:5173](http://127.0.0.1:5173)  
Vite проксирует `/api` → `http://127.0.0.1:8000`.

> Если в консоли Vite `ECONNREFUSED 127.0.0.1:8000` — backend не запущен. Сначала поднимите API.

### Production-режим (один процесс)

API раздаёт собранный фронт из `frontend/dist`:

```bash
cd frontend && npm install && npm run build && cd ..
source .venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

---

## Конфигурация (`.env`)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `RPC_URL` | `https://rpc.mainnet.chain.robinhood.com` | EVM JSON-RPC endpoint |
| `BLOCKSCOUT_API_KEY` | пусто | Опциональный ключ Blockscout Pro |
| `MCAP_THRESHOLD` | `15000` | Порог mcap (USD) для Early buyers |
| `LOG_CHUNK_SIZE` | `100000` | Размер блока для батча `eth_getLogs` |
| `RPC_CONCURRENCY` | `24` | Параллелизм RPC-запросов |
| `HONEYPOT_SIM_WHALE` | пусто | EOА с ≥0.05 ETH для eth_call симуляции honeypot; иначе auto |
| `HOST` | `0.0.0.0` | Хост API |
| `PORT` | `8000` | Порт API |

### Когда публичный RPC упирается в лимиты

1. **Public RPC** — бесплатно, для лёгкой нагрузки.
2. **[dRPC](https://drpc.org/)** — свой endpoint в `RPC_URL`.
3. **[QuickNode](https://www.quicknode.com/)** — удобнее для длинных `getLogs`.
4. **Blockscout Pro** — `BLOCKSCOUT_API_KEY` для метаданных / fallback по трансферам.

```env
RPC_URL=https://YOUR_ENDPOINT.robinhood-mainnet.quiknode.pro/YOUR_TOKEN/
```

---

## Как это работает

### Screener

```text
фильтры → каталог Blockscout (ERC-20)
       → батч-обогащение DexScreener
       → лучшая RH-пара по ликвидности
       → локальные фильтры
       → сортировка / truncate
```

Публичного filtered-catalog API у DexScreener для Robinhood нет, поэтому каталог берётся с Blockscout, а метрики — с DexScreener.

### Early buyers

1. Резолв пулов Uniswap V2/V3/V4 (DexScreener + factories WETH/USDG).
2. Стрим `Swap` с рождения пула; остановка, когда mcap ≥ порога.
3. Резолв покупателей через `Transfer` токена (PoolManager / routers → кошелёк).
4. `mcap = price_usd × totalSupply`.
5. Оставляем кошельки с покупкой при `mcap < threshold`.
6. Агрегация: токены, USD≈, mcap на первой покупке, число покупок.

Большинство мемкоинов на Robinhood торгуются на **Uniswap V4** (id пула — `bytes32`, не адрес пары).

---

## API

Все долгие операции — async jobs: `POST` создаёт задачу, `GET` поллит статус.

### Health

```http
GET /api/health
```

Ответ: `ok`, `chain_id`, `rpc_url`, `mcap_threshold`.

### Early buyers

```http
POST /api/parse
Content-Type: application/json

{
  "tokens": ["0x…"],
  "mcap_threshold": 15000,
  "exclude_honeypots": true
}
```

```http
GET /api/parse/{job_id}
```

Статусы: `queued` → `running` → `done` | `error`.  
В ответе: `progress`, `results[]` с `buyers`, `pool`, `error`.

### Screener

```http
POST /api/screen
Content-Type: application/json

{
  "min_liq": 5000,
  "max_liq": null,
  "min_mcap": 10000,
  "max_mcap": null,
  "min_traders": 20,
  "max_traders": null,
  "min_pair_age_hours": 1,
  "max_pair_age_hours": 168,
  "exclude_honeypots": true,
  "sort_by": "liquidity",
  "sort_order": "desc",
  "max_results": 500
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `min_liq` / `max_liq` | number \| null | Ликвидность USD |
| `min_mcap` / `max_mcap` | number \| null | Market cap USD |
| `min_traders` / `max_traders` | number \| null | Txns 24h (buys+sells) |
| `min_pair_age_hours` / `max_pair_age_hours` | number \| null | Возраст пары |
| `sort_by` | string | `liquidity` \| `market_cap` \| `traders` \| `pair_age` |
| `sort_order` | string | `asc` \| `desc` |
| `max_results` | int | 1–2000, по умолчанию 500 |
| `exclude_honeypots` | bool | По умолчанию `true` — скрывать honeypot (GMGN) |

```http
GET /api/screen/{job_id}
```

В `results[]`: адрес, symbol, price, liquidity, mcap, traders_24h, pair_age_hours, ссылки DexScreener/GMGN.

---

## Структура репозитория

```text
gnomode 2.0/
├── backend/app/
│   ├── main.py          # FastAPI: /api/parse, /api/screen, /api/health
│   ├── screener.py      # Screener: Blockscout + DexScreener + фильтры
│   ├── gmgn.py          # GMGN token security (honeypot / tax)
│   ├── goplus.py        # GoPlus checks (legacy fallback)
│   ├── honeypot_sim.py  # On-chain buy→sell eth_call (optional / legacy)
│   ├── security.py      # Combined honeypot gate (GMGN + Dex fallback)
│   ├── screen_jobs.py   # In-memory jobs для screener
│   ├── replay.py        # Replay свопов / early buyers
│   ├── pools.py         # Поиск пулов DexScreener + factories
│   ├── jobs.py          # In-memory jobs для parse
│   ├── blockscout.py    # Blockscout helpers
│   ├── chain.py         # RPC client + shared httpx
│   ├── models.py        # Pydantic-модели
│   ├── config.py        # Settings из .env
│   └── constants.py     # Адреса контрактов RH / Uniswap
├── frontend/src/
│   ├── App.tsx          # Навигация Early buyers / Screener
│   ├── ScreenerPage.tsx # UI screener
│   └── App.css          # Стили
├── scripts/
│   ├── dev-api.sh
│   └── dev-ui.sh
├── .env.example
└── README.md
```

---

## Интерфейс

- Вкладки **Early buyers** и **Screener** не размонтируются при переключении — результаты остаются на месте.
- Прогресс-бар во время долгих jobs.
- Таблицы с сортировкой по колонкам, текстовым фильтром и CSV-экспортом.
- Из Screener: чекбоксы → **Use in Early buyers** заполняет textarea адресами и переключает вкладку.

---

## Важные замечания

- Фильтр **traders** = сумма buy/sell txns за 24h из DexScreener, не число уникальных кошельков.
- Если первая on-chain цена уже даёт mcap ≥ порога, список early buyers будет пустым — это ожидаемо.
- Публичный RPC может быть медленным на длинной истории; для тяжёлых токенов лучше dRPC/QuickNode.
- USD для ETH/WETH берётся из DexScreener (fallback CoinGecko); USDG ≈ $1.
- Jobs хранятся **в памяти процесса** — после рестарта API старые `job_id` пропадают.

---

## Лицензия / репозиторий

Исходники: [github.com/Theseusure/gnomode2.0](https://github.com/Theseusure/gnomode2.0)
