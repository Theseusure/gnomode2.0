# Gnomode — сканер токенов Robinhood Chain

Веб-приложение для анализа токенов на **Robinhood Chain** (chain ID `4663`). Интерфейс на русском. Четыре основные функции:

1. **Скринер** — отбор токенов по фильтрам (ликвидность, возраст пары, трейдеры, market cap) из in-memory индекса за 24ч.
2. **Early buyers** — поиск кошельков, купивших токен при низком mcap (по умолчанию **$15 000**), с фильтрами кошельков.
3. **Автопарс** — по расписанию: скринер → парсинг → дедуп → алерты в **Telegram** (чат / топик форума).
4. **Follow-up** — таблица early buyers (1 токен = 1 сделка) → алерт на **2-й/3-й новый токен** только при низком mcap; опциональный sync в **RayBot** (EVM).

Репозиторий: [github.com/bunt13/gnomode](https://github.com/bunt13/gnomode)

---

## Возможности

### Скринер

- Держит **индекс токенов за последние 24ч** (новые пулы + обогащение метрик); UI показывает статус индекса.
- Фильтры применяются к индексу локально (быстро после прогрева).
- Отсекает honeypot через **GMGN token security** (с лёгким fallback по DexScreener).
- Локальные фильтры (min/max, пустое поле = без ограничения):
  - **liquidity** — `liquidity.usd`
  - **pair age** — возраст пары в часах
  - **traders** — `txns.h24.buys + sells` (прокси активности, не уникальные кошельки)
  - **mcap** — `marketCap`, иначе `fdv`
- Сортировка: liquidity / market_cap / traders / pair_age.
- Пресеты фильтров, экспорт CSV, перенос выбранных токенов во вкладку Early buyers.
- Состояние вкладок сохраняется при переключении.

### Early buyers

- Один или несколько адресов токенов.
- Перед тяжёлым replay — проверка honeypot через GMGN (можно отключить).
- Пулы Uniswap **V2 / V3 / V4** (DexScreener + on-chain factories WETH/USDG).
- Replay свопов до пересечения порога mcap → EOA early buyers.
- **Фильтры кошельков** (опционально):
  - баланс ETH (min/max);
  - время холда позиции (min/max);
  - число различных токенов за 7д (min/max, через Blockscout).
- Лог пайплайна в UI, экспорт CSV, ссылки на GMGN / Blockscout.

### Автопарс (Watch)

- Конфиг хранится на сервере (`backend/app/data/watch.json`, не в git).
- По интервалу (или «Запустить сейчас»):
  1. скрининг по сохранённым фильтрам токенов;
  2. **ATH-гейт** (`min_ath_mcap`, дефолт $50k): токены ниже порога — в hold (`watch_hold.json`), выше — qualify на парсинг early buyers;
  3. парсинг до `max_tokens_per_cycle` токенов с фильтрами кошельков (`mcap_threshold` ≈ early entry);
  4. дедуп пар **кошелёк + токен** (`watch_seen.json`);
  5. **сразу после каждого токена** — отправка новых кошельков в Telegram.
- **Догон** после долгого простоя (≥ 1 ч): сужает `max_pair_age` до окна простоя (макс. 24ч), прогревает индекс и **force re-enrich** hold-токенов (актуальный mcap/ATH). Короткие паузы / reload API догон не запускают.
- ATH пишется только пока процесс **живой и обогащает** индекс — при сне ноутбука пик можно не увидеть. Для непрерывного режима см. Docker + `keep-awake` ниже.
- Управление в UI: вкл/выкл, интервал, лимит токенов, фильтры, стоп, сброс счётчиков, очистка дедупа, проверка Telegram, живой лог.
- Гном в чате: «За работу!» при старте, периодические фразы (бантер), сообщение при падении/остановке процесса.

### Follow-up

- После успешной отправки early buyer из автопарса кошелёк попадает в **SQLite** (`backend/app/data/followup.db`, WAL).
- **Один токен = одна сделка.** Считаются distinct-токены: 1-я (discovery), затем 2-я / 3-я.
- Telegram-алерт только если `deal_index ∈ {2,3}` и `mcap_at_buy ≤ max_mcap_alert`. Высокий mcap — запись без уведомления.
- Фоновый poll Blockscout (`/addresses/{wallet}/token-transfers`) + оценка mcap через DexScreener.
- Опционально **RayBot** (ключи `RAYBOT_API_USER` / `RAYBOT_API_TOKEN` из `/api` в боте): add wallet + EVM-фильтры `evm_buys`, `evm_mc_trade_max` (логика как в [docs.raybot.app](https://docs.raybot.app/start)). Кошельки RH ведутся в RayBot через EVM.
- Опциональный webhook: `POST /api/followup/webhook/raybot` (нужен публичный HTTPS + `RAYBOT_WEBHOOK_AUTH`).
- UI: вкладка **Follow-up** — конфиг, лог, таблица кошельков/сделок.

---

## Стек

| Слой | Технологии |
|------|------------|
| Backend | Python 3.12+, FastAPI, web3.py, httpx, Pydantic |
| Frontend | Vite, React 19, TypeScript |
| Данные | публичный Robinhood RPC, DexScreener, Blockscout, GMGN |
| Алерты | Telegram Bot API |

---

## Быстрый старт: парсер на ноутбуке (Docker)

Нужны: [Docker](https://docs.docker.com/engine/install/) + Docker Compose, аккаунт Telegram.  
Один контейнер = API + UI. Состояние автопарса лежит на диске в `backend/app/data/` и переживает рестарты.

### 1. Клон и `.env`

```bash
git clone https://github.com/bunt13/gnomode.git
cd gnomode
cp .env.example .env
chmod +x scripts/*.sh
```

Откройте `.env` и заполните минимум:

```env
TELEGRAM_BOT_TOKEN=...      # @BotFather → /newbot
TELEGRAM_CHAT_ID=...        # личный чат или группа (-100…)
# TELEGRAM_TOPIC_ID=...     # только для топика форума

# Рекомендуется для автопарса (публичный RPC часто даёт 429):
# RPC_URL=https://YOUR_ENDPOINT...
# RPC_CONCURRENCY=3
```

Как взять `TELEGRAM_CHAT_ID`: напишите боту `/start`, затем откройте  
`https://api.telegram.org/bot<TOKEN>/getUpdates` и найдите `"chat":{"id": ...}`.  
В супергруппе id обычно вида `-100…`.

### 2. Запуск

**Непрерывно на ноутбуке** (блокирует idle/sleep, терминал должен быть открыт):

```bash
./scripts/keep-awake.sh
```

Первая сборка займёт несколько минут. Дальше: [http://127.0.0.1:8000](http://127.0.0.1:8000)

**В фоне** (Docker сам поднимет после ребута; **сон ноутбука не блокируется** — возможны пропуски ATH):

```bash
docker compose up -d --build
docker compose logs -f
```

Остановка: `Ctrl+C` у `keep-awake`, либо `docker compose down`.

### 3. Включить автопарс в UI

1. Откройте [http://127.0.0.1:8000](http://127.0.0.1:8000) → вкладка **Автопарс**.
2. **Проверить Telegram** — должен прийти тестовый пинг.
3. Задайте фильтры (см. профиль ниже) → **Вкл** автопарс (или «Запустить сейчас»).
4. Смотрите живой лог: скринер → hold/qualify → парсинг → отправка в Telegram.

Пока индекс 24ч прогревается (первый запуск), первый цикл может подождать — это нормально.

### Рекомендуемый профиль

| Параметр | Значение | Зачем |
|----------|----------|--------|
| Интервал | 5–15 мин | чаще — свежее ATH, реже — меньше нагрузка на RPC |
| `max_tokens_per_cycle` | 10–20 на публичном RPC | иначе 429 |
| `min_ath_mcap` | целевой ATH токена (напр. 50000) | qualify только после пампа |
| `wallet.mcap_threshold` | early entry (напр. 15000) | кошельки, зашедшие «рано» |
| Telegram | обязателен | без него цикл не считается успешным |

### Важно про сон ноутбука

ATH пишется **только пока контейнер жив и обогащает** индекс. Если ноутбук уснул в момент пампа — пик можно не увидеть, токен останется в hold.

- Для 24/7 на ноутбуке используйте `./scripts/keep-awake.sh` (не `-d`), либо отключите suspend / не закрывайте крышку.
- Тот же `docker compose` можно перенести на VPS — логика та же, риска сна нет.

### State на диске (не коммитить)

| Файл | Назначение |
|------|------------|
| `backend/app/data/watch.json` | конфиг автопарса |
| `watch_seen.json` | дедуп кошелёк+токен |
| `watch_state.json` | время последнего успеха (догон) |
| `watch_hold.json` | очередь ATH + уже распарсенные токены |

### Частые команды

```bash
docker compose ps                 # статус
docker compose logs -f --tail=100 # лог
docker compose up -d --build      # пересобрать после git pull
docker compose down               # остановить
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/watch/status
```

---

## Разработка (без Docker)

### Backend

```bash
cp .env.example .env   # если ещё нет
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
chmod +x scripts/*.sh
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
Если `ECONNREFUSED 127.0.0.1:8000` — сначала запустите API.

### Production без Docker (один процесс)

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
| `BLOCKSCOUT_API_KEY` | пусто | Опциональный ключ Blockscout Pro |
| `MCAP_THRESHOLD` | `15000` | Порог mcap (USD) по умолчанию |
| `LOG_CHUNK_SIZE` | `100000` | Размер окна `eth_getLogs` |
| `RPC_CONCURRENCY` | `6` | Параллелизм RPC (на публичной ноде лучше 2–6) |
| `HONEYPOT_SIM_WHALE` | пусто | EOА для eth_call honeypot-симуляции |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Слушатель API |
| `TELEGRAM_BOT_TOKEN` | пусто | Токен бота (@BotFather) |
| `TELEGRAM_CHAT_ID` | пусто | Chat id (или задайте в UI автопарса) |
| `TELEGRAM_TOPIC_ID` | пусто | `message_thread_id` топика форума |
| `WATCH_*_PATH` | `backend/app/data/…` | Пути `watch.json` / `watch_seen.json` / `watch_state.json` / `watch_hold.json` |

### Telegram

1. Создайте бота у [@BotFather](https://t.me/BotFather), вставьте токен в `.env`.
2. Напишите боту `/start` (личный чат) **или** добавьте бота в группу/форум.
3. Укажите числовой `TELEGRAM_CHAT_ID` (для супергрупп обычно `-100…`).
4. Для топика форума — `TELEGRAM_TOPIC_ID`.
5. В UI: **Автопарс → Проверить Telegram**.

`chat not found` / `401 Unauthorized` — бот не видит чат или неверный/отозванный токен.

### Когда публичный RPC упирается в 429

1. Public RPC — для лёгкой нагрузки; при автопарсе 429 + retry — норма.
2. Снизьте `RPC_CONCURRENCY` (например `2–3`) и/или `max_tokens_per_cycle`.
3. [dRPC](https://drpc.org/) / [QuickNode](https://www.quicknode.com/) — свой `RPC_URL`.
4. Blockscout Pro — `BLOCKSCOUT_API_KEY` для метаданных и метрик кошельков.

```env
RPC_URL=https://YOUR_ENDPOINT.robinhood-mainnet.quiknode.pro/YOUR_TOKEN/
RPC_CONCURRENCY=6
```

---

## Как это работает

### Скринер / индекс

```text
фон: scan новых пулов → enrich → индекс 24ч
UI/API: фильтры → срез индекса → honeypot (GMGN) → сортировка
```

### Early buyers

1. Резолв пулов V2/V3/V4.
2. Стрим свопов с рождения пула; стоп при mcap ≥ порога.
3. Резолв покупателей через `Transfer`.
4. Фильтры кошельков: баланс → холд → токены за 7д.
5. Агрегация и выдача в job.

### Автопарс

```text
расписание / Run now
  → [догон] ensure_ready + force enrich hold (ATH)
  → screen(filters)
  → ATH gate: hold | qualify
  → для каждого qualify[:max_tokens]:
       parse + wallet filters
       → новые (не в seen) → Telegram сразу
       → mark_seen / mark_token_parsed
  → следующий цикл через interval_sec
```

Большинство мемкоинов на Robinhood торгуются на **Uniswap V4** (id пула — `bytes32`).

**Ограничение ATH:** пик mcap — это max наблюдаемых сэмплов DexScreener, пока сервис работает. Исторический ATH за время простоя DexScreener не отдаёт; догон обновляет текущий mcap hold-токенов, но «пропущенный» памп может остаться незамеченным.

---

## API

Долгие операции Early buyers / Screener — async jobs: `POST` создаёт задачу, `GET` поллит статус.

### Health / индекс

```http
GET  /api/health
GET  /api/index/status
POST /api/index/refresh
```

### Early buyers

```http
POST /api/parse
Content-Type: application/json

{
  "tokens": ["0x…"],
  "mcap_threshold": 15000,
  "exclude_honeypots": true,
  "min_wallet_balance_eth": 0.01,
  "max_wallet_balance_eth": null,
  "min_hold_time_minutes": 1,
  "max_hold_time_minutes": null,
  "min_tokens_traded_7d": 2,
  "max_tokens_traded_7d": 5
}
```

```http
GET /api/parse/{job_id}
```

Статусы: `queued` → `running` → `done` | `error`.  
В ответе: `progress`, `log[]`, `results[]` с `buyers`.

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

```http
GET /api/screen/{job_id}
```

### Автопарс

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/watch` | Текущий конфиг |
| `PUT` | `/api/watch` | Сохранить конфиг (будит планировщик) |
| `GET` | `/api/watch/status` | Статус, счётчики, лог, next_run |
| `POST` | `/api/watch/run` | Запустить цикл сейчас |
| `POST` | `/api/watch/stop` | Принудительная остановка цикла |
| `POST` | `/api/watch/reset-counters` | Сброс счётчиков UI |
| `POST` | `/api/watch/test-telegram` | getMe + пинг в чат/топик |
| `POST` | `/api/watch/clear-seen` | Очистить дедуп |

### Follow-up

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/followup` | Конфиг |
| `PUT` | `/api/followup` | Сохранить конфиг |
| `GET` | `/api/followup/status` | Статус цикла / лог |
| `GET` | `/api/followup/wallets` | Таблица кошельков + deals |
| `POST` | `/api/followup/run` | Запустить цикл сейчас |
| `POST` | `/api/followup/stop` | Стоп |
| `POST` | `/api/followup/test-telegram` | Пинг Telegram |
| `POST` | `/api/followup/test-raybot` | Проверка RayBot API |
| `POST` | `/api/followup/webhook/raybot` | Webhook от RayBot (опционально) |

Конфиг: `enabled`, `interval_sec`, `max_mcap_alert`, `alert_on_deals` (по умолчанию `[2,3]`), `max_deals`, chat/topic, `raybot_enabled`, `ingest_from_watch`.

---

## Структура репозитория

```text
gnomode 2.0/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI routes
│   │   ├── watch.py           # Планировщик автопарса
│   │   ├── watch_store.py     # JSON: config / seen / last_success
│   │   ├── followup.py        # Follow-up: 2-й/3-й токен @ low mcap
│   │   ├── followup_store.py  # SQLite wallets/deals
│   │   ├── raybot.py          # RayBot API (EVM filters / sync)
│   │   ├── telegram.py        # Bot API (send, getMe, test)
│   │   ├── gnome_phrases.py   # Фразы гнома (~134)
│   │   ├── gnome_banter.py    # Периодический бантер
│   │   ├── gnome_lifecycle.py # «За работу!» / смерть
│   │   ├── token_index.py     # Индекс токенов 24ч
│   │   ├── screener.py
│   │   ├── replay.py          # Early buyers
│   │   ├── wallet_metrics.py  # Баланс / холд / tokens 7d
│   │   ├── pools.py / chain.py / blockscout.py / gmgn.py / …
│   │   ├── models.py / config.py / constants.py
│   │   └── data/              # runtime JSON + followup.db (gitignore)
│   ├── tests/
│   └── pytest.ini
├── frontend/src/
│   ├── App.tsx                # Early buyers + вкладки
│   ├── ScreenerPage.tsx
│   ├── WatchPage.tsx          # Автопарс
│   ├── FollowupPage.tsx       # Follow-up таблица
│   ├── FilterPresets.tsx
│   └── App.css
├── scripts/dev-api.sh | dev-ui.sh
├── .env.example
└── README.md
```

---

## Интерфейс

- Вкладки **Early buyers**, **Скринер**, **Автопарс**, **Follow-up** не размонтируются — результаты и лог не сбрасываются.
- Прогресс и пошаговый лог во время долгих операций.
- Таблицы: сортировка, текстовый фильтр, CSV.
- Из скринера: чекбоксы → перенос адресов в Early buyers.
- Автопарс: статус цикла, следующий запуск, лог, кнопки стоп / Telegram / дедуп.

---

## Важные замечания

- **traders** = сумма buy/sell txns за 24h, не уникальные кошельки.
- Фильтр **токенов за 7д** очень жёсткий: early buyer часто имеет 1 токен (текущий) или >5 у активных — из‑за этого автопарс может находить 0 кош. при ненулевом числе early buyers.
- Если первая on-chain цена уже даёт mcap ≥ порога — список early buyers пуст (ожидаемо).
- Публичный RPC: `429 Too Many Requests` + retry — нормальная картина под нагрузкой.
- Parse/screen jobs — **в памяти процесса**; после рестарта API старые `job_id` пропадают.
- Состояние автопарса (конфиг, seen, last_success) — на диске в `backend/app/data/`.
- Секреты только в `.env` (не коммитить).

---

## Лицензия / репозиторий

Исходники: [github.com/bunt13/gnomode](https://github.com/bunt13/gnomode)
