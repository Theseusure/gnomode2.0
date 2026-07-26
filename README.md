# Gnomode 2.x — сканер и follow-up кошельков на Robinhood Chain

Веб-приложение для команды, которая ищет **ранних покупателей** мемкоинов на **Robinhood Chain** (chain ID `4663`) и следит, берут ли они **следующие токены снова на низком mcap**.

Интерфейс на русском. Один процесс = API + UI (Docker или локально).

---

## Какую ссылку дать коллегам

| Версия | Репозиторий | Ссылка |
|--------|-------------|--------|
| **2.2** (актуальная: Follow-up + свой Telegram-бот) | [Theseusure/gnomode2.0](https://github.com/Theseusure/gnomode2.0) | [tree/v2.2.0](https://github.com/Theseusure/gnomode2.0/tree/v2.2.0) · ветка `feature/wallet-followup` |
| **2.2** (зеркало) | [bunt13/gnomode](https://github.com/bunt13/gnomode) | [tree/v2.2.0](https://github.com/bunt13/gnomode/tree/v2.2.0) · ветка `v2` |
| **2.0** | [bunt13/gnomode](https://github.com/bunt13/gnomode) | [tree/v2.0.0](https://github.com/bunt13/gnomode/tree/v2.0.0) |

Клон актуальной 2.2:

```bash
git clone --branch v2.2.0 https://github.com/Theseusure/gnomode2.0.git
cd gnomode2.0
```

Запасной клон с bunt13:

```bash
git clone --branch v2.2.0 https://github.com/bunt13/gnomode.git
cd gnomode
```

> В `bunt13/gnomode` ветка `main` пока на **v1.x**. Для 2.x берите тег `v2.2.0` / ветку `v2`, не `main`.

---

## Что умеет продукт (5 вкладок)

1. **Скринер** — живой индекс токенов за ~24ч, фильтры (liq / age / traders / mcap), honeypot-отсев.
2. **Кошельки (Early buyers)** — по адресу токена: кто купил **до** порога mcap (по умолчанию **$15 000**).
3. **Автопарс** — по расписанию: скринер → ATH-гейт → early buyers → **Telegram** (расписание и чат).
4. **Follow-up** — сохраняет этих кошельков в таблицу и шлёт алерт, когда они берут **2-й или 3-й новый токен снова на низком mcap** (высокий mcap — без уведомления). **Свой Telegram-бот** с фильтрами и командами (RayBot не нужен).
5. **Настройки** — фильтры **токена** и **первой сделки** кошелька для автопарса (и порог mcap early buyers).

### Идея Follow-up одной фразой

> Нашли кошелёк, который зашёл в токен рано (низкий mcap) → положили в таблицу → если он потом заходит во **второй/третий новый** токен снова рано — пишем в Telegram. Если заходит уже на высоком mcap — молчим.

Правило учёта: **один токен = одна сделка** (докупки того же токена не считаются новой сделкой).

---

## Быстрый старт (Docker на ноутбуке)

Нужны: [Docker](https://docs.docker.com/engine/install/) + Compose, Telegram-бот.

### 1. Клон и `.env`

```bash
git clone --branch v2.0.0 https://github.com/bunt13/gnomode.git
cd gnomode
cp .env.example .env
# Linux/macOS:
chmod +x scripts/*.sh
```

Минимум в `.env`:

```env
TELEGRAM_BOT_TOKEN=...      # @BotFather → /newbot
TELEGRAM_CHAT_ID=...        # личный чат или группа (-100…)
# TELEGRAM_TOPIC_ID=...     # только для топика форума

# Для автопарса лучше свой RPC (публичный часто даёт 429):
# RPC_URL=https://YOUR_ENDPOINT...
# RPC_CONCURRENCY=3

# Follow-up + RayBot (опционально):
# RAYBOT_API_USER=...       # команда /api в RayBot
# RAYBOT_API_TOKEN=...
# RAYBOT_BOT=1
```

`TELEGRAM_CHAT_ID`: напишите боту `/start`, откройте  
`https://api.telegram.org/bot<TOKEN>/getUpdates` → `"chat":{"id": ...}`.

### 2. Запуск

**Непрерывно (рекомендуется для ATH)** — блокирует сон ноутбука, терминал открыт:

```bash
./scripts/keep-awake.sh
```

UI: [http://127.0.0.1:8000](http://127.0.0.1:8000)

**В фоне** (после ребута поднимется сам; сон ноутбука **не** блокируется → можно пропустить ATH):

```bash
docker compose up -d --build
docker compose logs -f
```

Стоп: `Ctrl+C` у keep-awake, или `docker compose down`.

### 3. Первый рабочий день в UI

**Автопарс**

1. Вкладка **Настройки** → задайте фильтры токена и первой сделки → **Сохранить**.
2. Вкладка **Автопарс** → **Проверить Telegram** (должен прийти пинг).
3. Вкл. расписание или «Запустить сейчас» (сохранение автопарса **не** перезаписывает фильтры из Настроек).
4. Смотрите лог: скринер → hold/qualify → парсинг → Telegram.

**Follow-up**

1. Вкладка **Follow-up**.
2. Включите **Ingest** (брать early buyers из автопарса).
3. Задайте **Max mcap для алерта** (например `15000`).
4. При необходимости включите **RayBot sync** (нужны ключи в `.env`).
5. **Сохранить** → **Вкл** → при желании «Запустить сейчас».
6. В таблице появятся кошельки с deal `#1`; на `#2`/`#3` @ low mcap придёт отдельный алерт.

Пока индекс 24ч прогревается в первый раз, автопарс может подождать — это нормально.

### Рекомендуемый профиль автопарса

| Параметр | Значение | Зачем |
|----------|----------|--------|
| Интервал | 5–15 мин | чаще — свежее ATH; реже — меньше нагрузка |
| `max_tokens_per_cycle` | 10–20 на публичном RPC | иначе 429 |
| `min_ath_mcap` | целевой ATH (напр. 50000) | парсить только после пампа |
| `wallet.mcap_threshold` | early entry (напр. 15000) | «ранний» вход |
| Telegram | обязателен | без него цикл не считается успешным |

### Сон ноутбука

ATH пишется **только пока процесс жив и обогащает** индекс. Уснули в момент пампа — пик могли не увидеть, токен останется в hold.

- 24/7 на ноутбуке: `./scripts/keep-awake.sh` (не `-d`), или отключите suspend.
- На VPS тот же `docker compose` — риска сна нет.

---

## Возможности подробнее

### Скринер

- Индекс токенов за последние ~24ч (новые пулы + обогащение метрик).
- Фильтры локально по индексу (быстро после прогрева):
  - **liquidity** — `liquidity.usd`
  - **pair age** — возраст пары в часах
  - **traders** — `txns.h24.buys + sells` (**не** уникальные кошельки)
  - **mcap** — `marketCap`, иначе `fdv`
- Honeypot: GMGN token security (+ лёгкий fallback DexScreener).
- Пресеты, CSV, перенос выбранных адресов во вкладку «Кошельки».
- Состояние вкладок сохраняется при переключении.

### Early buyers

- Один или несколько адресов токенов.
- Пулы Uniswap **V2 / V3 / V4** (DexScreener + on-chain factories WETH/USDG).
- Replay свопов до порога mcap → EOA early buyers.
- Опциональные фильтры кошелька: баланс ETH, время холда, число разных токенов за 7д (Blockscout).
- Лог пайплайна, CSV, ссылки GMGN / Blockscout.

### Автопарс (Watch)

Конфиг на диске: `backend/app/data/watch.json` (не в git).

Цикл:

1. Скрининг по сохранённым фильтрам.
2. **ATH-гейт** (`min_ath_mcap`, дефолт $50k): ниже порога → hold; выше → qualify.
3. Парсинг до `max_tokens_per_cycle` с фильтрами кошельков.
4. Дедуп пары **кошелёк + токен** (`watch_seen.json`).
5. Сразу после каждого токена — новые кошельки в Telegram.

**Догон** после простоя ≥ 1 ч: сужает `max_pair_age`, прогревает индекс, force re-enrich hold. Короткие паузы / reload API догон не запускают.

В UI: вкладка **Настройки** — фильтры токена и 1-й сделки; вкладка **Автопарс** — вкл/выкл, интервал, лимиты, стоп, сброс счётчиков, очистка дедупа, тест Telegram, живой лог.  
Гном в чате: старт / бантер / сообщение при падении процесса.

### Follow-up + свой Telegram-бот (без RayBot)

| Шаг | Что происходит |
|-----|----------------|
| Discovery | После успешного Telegram из автопарса → deal **#1** в SQLite (`followup.db`, WAL) |
| Учёт | Distinct-токены: #1, #2, #3… Один токен = одна сделка |
| Алерт | Только если `deal_index ∈ {2,3}` **и** нативные фильтры mcap/usd пройдены |
| Высокий mcap | Сделка пишется в таблицу, **уведомления нет** |
| Стоп | После `max_deals` (по умолчанию 3) статус кошелька `done` |
| Мониторинг | Poll Blockscout `token-transfers` + mcap с DexScreener |
| **Свой бот** | Long-poll на том же `TELEGRAM_BOT_TOKEN`: `/status` `/wallets` `/filters` `/on` `/off` `/run` `/set_max_mcap` `/set_min_mcap` `/set_interval` `/help` |
| RayBot | **Не нужен.** `raybot.py` оставлен как legacy (`raybot_enabled=false`) |

#### Фильтры алерта (нативные)

| Фильтр | Смысл |
|--------|--------|
| `max_mcap_alert` | Алерт только если mcap покупки ≤ порога |
| `min_mcap_alert` | Опциональный пол mcap |
| `min_bought_usd` / `max_bought_usd` | Размер покупки (если известен) |
| `alert_on_deals` | По умолчанию `[2, 3]` |
| `buys_only` | Только входящие токены с контракта (DEX) |

Файлы состояния Follow-up (не коммитить):

| Файл | Назначение |
|------|------------|
| `backend/app/data/followup.db` | SQLite: wallets / deals / alert_log |
| `backend/app/data/followup.json` | конфиг Follow-up |

---

## Стек

| Слой | Технологии |
|------|------------|
| Backend | Python 3.12+, FastAPI, web3.py, httpx, Pydantic |
| Frontend | Vite, React 19, TypeScript |
| Данные | Robinhood RPC, DexScreener, Blockscout, GMGN |
| Алерты | Telegram Bot API; опционально RayBot |
| Хранение Follow-up | SQLite (WAL) |

---

## Разработка без Docker

### Backend

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
./scripts/dev-api.sh
```

API: [http://127.0.0.1:8000](http://127.0.0.1:8000)

```bash
cd backend && ../.venv/bin/pytest -q
```

### Frontend (второй терминал)

```bash
./scripts/dev-ui.sh
```

UI: [http://127.0.0.1:5173](http://127.0.0.1:5173) — Vite проксирует `/api` → backend.

### Один процесс (production без Docker)

```bash
cd frontend && npm install && npm run build && cd ..
source .venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

---

## Конфигурация (`.env`)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `RPC_URL` | публичный RH RPC | EVM JSON-RPC |
| `BLOCKSCOUT_API_KEY` | пусто | Blockscout Pro |
| `MCAP_THRESHOLD` | `15000` | Порог early-buyer mcap (USD) |
| `LOG_CHUNK_SIZE` | `100000` | Окно `eth_getLogs` |
| `RPC_CONCURRENCY` | `6` | На публичной ноде лучше 2–6 |
| `HONEYPOT_SIM_WHALE` | пусто | EOА для honeypot eth_call |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Слушатель API |
| `TELEGRAM_BOT_TOKEN` | пусто | Токен @BotFather |
| `TELEGRAM_CHAT_ID` | пусто | Chat id (можно переопределить в UI) |
| `TELEGRAM_TOPIC_ID` | пусто | Топик форума |
| `WATCH_*_PATH` | `backend/app/data/…` | Пути JSON автопарса |
| `FOLLOWUP_DB_PATH` | `…/followup.db` | SQLite Follow-up |
| `FOLLOWUP_CONFIG_PATH` | `…/followup.json` | Конфиг Follow-up |
| `RAYBOT_API_USER` | пусто | Из `/api` в RayBot |
| `RAYBOT_API_TOKEN` | пусто | Из `/api` в RayBot |
| `RAYBOT_BOT` | `1` | Номер бота RayBot |
| `RAYBOT_BASE_URL` | `https://webapi.raybot.app` | API RayBot |
| `RAYBOT_WEBHOOK_AUTH` | пусто | Заголовок Authorization для webhook |

### Telegram — чеклист

1. Создать бота у [@BotFather](https://t.me/BotFather), токен → `.env`.
2. `/start` боту или добавить в группу/форум.
3. Числовой `TELEGRAM_CHAT_ID` (супергруппы часто `-100…`).
4. При топике — `TELEGRAM_TOPIC_ID`.
5. UI: **Автопарс → Проверить Telegram** (и то же на Follow-up при отдельном чате).

`chat not found` / `401` — бот не видит чат или токен неверный.

### RayBot — чеклист

1. В RayBot отправить `/api` → получить `api_user` и `token`.
2. Прописать `RAYBOT_API_USER` / `RAYBOT_API_TOKEN` в `.env`.
3. Follow-up → включить **RayBot sync** → Сохранить → **Проверить RayBot**.
4. Фильтры на стороне RayBot выставляются кодом: buys only + `evm_mc_trade_max` = ваш `max_mcap_alert`.

### RPC 429

1. На публичном RPC retry при автопарсе — норма.
2. Снизьте `RPC_CONCURRENCY` и/или `max_tokens_per_cycle`.
3. Свой endpoint: [dRPC](https://drpc.org/) / [QuickNode](https://www.quicknode.com/).
4. `BLOCKSCOUT_API_KEY` — для метрик кошельков.

---

## Как это работает (схемы)

### Скринер / индекс

```text
фон: scan новых пулов → enrich → индекс 24ч
UI/API: фильтры → срез → honeypot (GMGN) → сортировка
```

### Early buyers

1. Резолв пулов V2/V3/V4.
2. Стрим свопов с рождения пула; стоп при mcap ≥ порога.
3. Покупатели через `Transfer`.
4. Фильтры: баланс → холд → токены 7д.
5. Ответ job.

### Автопарс

```text
расписание / Run now
  → [догон] ensure_ready + force enrich hold (ATH)
  → screen(filters)
  → ATH gate: hold | qualify
  → для каждого qualify[:max_tokens]:
       parse + wallet filters
       → новые (не в seen) → Telegram
       → mark_seen
       → Follow-up ingest (deal #1), если включено
  → следующий цикл
```

### Follow-up

```text
deal #1 (из автопарса, low mcap) → SQLite + опционально RayBot
  → poll / webhook: новый distinct-токен
       → mcap ≤ порога и index 2|3 → Telegram Follow-up
       → mcap высокий → только запись
  → после max_deals → status=done
```

Большинство мемкоинов на RH торгуются на **Uniswap V4** (id пула — `bytes32`).

**Ограничение ATH:** пик = max сэмплов DexScreener, пока сервис работает. Исторический ATH за простой DexScreener не отдаёт.

---

## API (кратко)

Долгие Early buyers / Screener — async jobs: `POST` создаёт задачу, `GET` поллит статус.

| Область | Примеры |
|---------|---------|
| Health / индекс | `GET /api/health`, `GET /api/index/status`, `POST /api/index/refresh` |
| Early buyers | `POST /api/parse`, `GET /api/parse/{job_id}` |
| Screener | `POST /api/screen`, `GET /api/screen/{job_id}` |
| Автопарс | `GET/PUT /api/watch`, `…/status`, `…/run`, `…/stop`, `…/test-telegram`, `…/clear-seen` |
| Follow-up | `GET/PUT /api/followup`, `…/status`, `…/wallets`, `…/run`, `…/stop`, `…/test-telegram`, `…/test-raybot`, `…/webhook/raybot` |

Пример parse:

```http
POST /api/parse
Content-Type: application/json

{
  "tokens": ["0x…"],
  "mcap_threshold": 15000,
  "exclude_honeypots": true,
  "min_wallet_balance_eth": 0.01,
  "min_hold_time_minutes": 1,
  "min_tokens_traded_7d": 2,
  "max_tokens_traded_7d": 5
}
```

Конфиг Follow-up (`PUT /api/followup`): `enabled`, `interval_sec`, `max_mcap_alert`, `alert_on_deals` (дефолт `[2,3]`), `max_deals`, chat/topic, `raybot_enabled`, `ingest_from_watch`.

---

## State на диске (не коммитить)

| Файл | Назначение |
|------|------------|
| `watch.json` | конфиг автопарса |
| `watch_seen.json` | дедуп кошелёк+токен |
| `watch_state.json` | last success (догон) |
| `watch_hold.json` | ATH-hold + parsed tokens |
| `followup.json` | конфиг Follow-up |
| `followup.db` | таблица кошельков и сделок |

Секреты только в `.env`.

### Частые команды

```bash
docker compose ps
docker compose logs -f --tail=100
docker compose up -d --build
docker compose down
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/watch/status
curl -s http://127.0.0.1:8000/api/followup/status
```

---

## Структура репозитория

```text
gnomode/
├── backend/app/
│   ├── main.py              # FastAPI (version в OpenAPI)
│   ├── watch.py / watch_store.py
│   ├── followup.py / followup_store.py / followup_bot.py
│   ├── raybot.py                # legacy sync (optional)
│   ├── telegram.py
│   ├── token_index.py / screener.py / replay.py
│   ├── wallet_metrics.py / pools.py / blockscout.py / …
│   └── data/                # runtime (gitignore)
├── backend/tests/
├── frontend/src/
│   ├── App.tsx
│   ├── ScreenerPage.tsx / WatchPage.tsx / FollowupPage.tsx
│   └── …
├── scripts/                 # keep-awake, dev-api, dev-ui
├── .env.example
└── README.md
```

Правило коммитов команды: [`.cursor/rules/commit-messages.mdc`](.cursor/rules/commit-messages.mdc) — сообщения на русском, с подробным телом.

---

## Важные ограничения

- **traders** = сумма buy/sell txns за 24h, не уникальные адреса.
- Фильтр **токенов за 7д** жёсткий: early buyer часто с 1 токеном или >5 у активных → автопарс может отдать 0 кош. при ненулевом числе early buyers.
- Если первая on-chain цена уже ≥ порога mcap — early buyers пуст (ожидаемо).
- Публичный RPC: `429` + retry под нагрузкой — норма.
- Parse/screen jobs живут **в памяти процесса**; после рестарта старые `job_id` пропадают.
- Follow-up не алертит на high-mcap и не считает докупки того же токена отдельными сделками.

---

## Репозитории

- Актуальный снимок **2.2**: [Theseusure/gnomode2.0 @ v2.2.0](https://github.com/Theseusure/gnomode2.0/tree/v2.2.0)
- Зеркало / bunt13: [bunt13/gnomode @ v2.2.0](https://github.com/bunt13/gnomode/tree/v2.2.0)
- Ранний снимок 2.0: [bunt13/gnomode @ v2.0.0](https://github.com/bunt13/gnomode/tree/v2.0.0)
