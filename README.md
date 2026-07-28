# Gnomode 2.x — сканер и follow-up кошельков на Robinhood Chain

Веб-приложение для команды, которая ищет **ранних покупателей** мемкоинов на **Robinhood Chain** (chain ID `4663`) и следит, берут ли они **следующие токены снова на низком mcap**.

Интерфейс на русском. Один процесс = API + UI (Docker или локально).

**Полная инструкция для команды (настройка + использование):**  
[docs/USER_GUIDE.md](docs/USER_GUIDE.md) · на GitHub: [открыть](https://github.com/Theseusure/gnomode2.0/blob/feature/followup-ray-filters/docs/USER_GUIDE.md)

---

## Какую ссылку дать коллегам

| Версия | Репозиторий | Ссылка |
|--------|-------------|--------|
| **2.2+** (Follow-up + фильтры buy/transfer) | [Theseusure/gnomode2.0](https://github.com/Theseusure/gnomode2.0) | ветка `feature/followup-ray-filters` (поверх `feature/wallet-followup`) |
| **2.2** (базовый Follow-up) | [Theseusure/gnomode2.0](https://github.com/Theseusure/gnomode2.0) | [tree/v2.2.0](https://github.com/Theseusure/gnomode2.0/tree/v2.2.0) · ветка `feature/wallet-followup` |
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

### Гид: как правильно искать (типичный день)

Цель: найти кошельки, которые заходят в новые токены **рано** (низкий mcap), сохранить их и узнать, когда они сделают это снова.

1. **Настройки** — задайте «сетку» поиска:
   - фильтры токена (ликвидность, возраст пары, traders, mcap) — что автопарс вообще рассматривает;
   - `mcap_threshold` / порог 1-й сделки (часто **15000**) — «ранний» вход;
   - опционально баланс ETH, hold time, токены за 7д — отсев шума;
   - нажмите **Сохранить** (автопарс подхватит эти фильтры, не перезаписывайте их слепо с вкладки Автопарс).
2. **Скринер** (по желанию) — гляньте живой рынок, пресеты, перенос адресов в «Кошельки» для ручного разбора.
3. **Кошельки** — ручной разбор одного токена: вставили адрес → early buyers → CSV / ссылки.
4. **Автопарс** — включили расписание или «Запустить сейчас» → лог: screen → ATH → parse → Telegram. Это **источник** deal #1 для Follow-up.
5. **Follow-up** — Ingest + фильтры алертов + Вкл → таблица наполняется; алерты на #2/#3 @ low mcap.

Без шага 4 (успешный автопарс + Telegram) Follow-up останется пустым — так задумано.

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
2. Включите **Ingest** (брать early buyers из автопарса после успешного Telegram).
3. Задайте **Max mcap для алерта** (например `15000`) — и при желании Min mcap / Min–Max buy USD.
4. Оставьте **buys_only** включённым (только покупки с DEX). **track_transfers** включайте только если нужны входящие переводы от обычных кошельков (и тогда `buys_only` лучше выключить).
5. Включите **Команды бота**, если хотите управлять фильтрами из Telegram (`/help`).
6. **Сохранить** → **Вкл** → при желании «Запустить сейчас».
7. В таблице появятся кошельки с deal `#1` (баланс ETH, токены за 7д, история сделок). На `#2`/`#3` @ low mcap придёт отдельный алерт; на высоком mcap — только строка в таблице без уведомления.

> Без работающего **Автопарса** и успешной отправки early buyers в Telegram таблица Follow-up сама не наполнится — это ожидаемо.

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

Follow-up — это «вторая линия» после автопарса: сохраняем кошельки, которые уже доказали ранний вход, и следим, возьмут ли они **ещё один новый токен** снова рано.

#### Как пользоваться (пошагово для новичка)

1. Сначала настройте и запустите **Автопарс** (см. выше) — без него Follow-up пустой.
2. Откройте вкладку **Follow-up**.
3. Включите **Автопарс → таблица (Ingest)** — иначе deal #1 не пишется.
4. Выставьте фильтры алертов (см. таблицу ниже). Стартовый профиль команды:
   - `max_mcap_alert = 15000`
   - `alert_on_deals = [2, 3]` (меняется через API/конфиг; в UI по умолчанию так)
   - `buys_only = on`, `track_transfers = off`
   - `interval_sec = 300` (раз в 5 минут опрос watching-кошельков)
5. Нажмите **Сохранить**, затем включите **Follow-up Вкл**.
6. Нажмите **Проверить Telegram** — должен прийти тестовый пинг.
7. Дождитесь, пока автопарс пришлёт early buyers: в таблице появятся строки со статусом `watching` и deal `#1`.
8. Когда тот же кошелёк купит **другой** токен:
   - если mcap в момент опроса ≤ порога и номер сделки 2 или 3 → придёт Telegram-алерт;
   - если mcap высокий → сделка всё равно сохранится, алерта не будет;
   - повторная покупка **того же** токена новой сделкой не считается.

#### Что происходит под капотом

| Шаг | Что происходит |
|-----|----------------|
| Discovery | После **успешного** Telegram из автопарса → deal **#1** в SQLite (`followup.db`, режим WAL) |
| Учёт | Distinct-токены: #1, #2, #3… **Один токен = одна сделка** |
| Алерт | Только если `deal_index ∈ {2,3}` **и** нативные фильтры mcap/USD пройдены |
| Высокий mcap | Сделка пишется в таблицу, **уведомления нет** |
| Стоп | После `max_deals` (по умолчанию 3) статус кошелька `done` |
| Мониторинг | Poll Blockscout `token-transfers` + mcap/price с DexScreener; сумма покупки = amount × priceUsd |
| **Свой бот** | Long-poll на том же `TELEGRAM_BOT_TOKEN` (список команд ниже) |
| RayBot | **Не нужен.** `raybot.py` оставлен как legacy (`raybot_enabled=false`) |

#### Фильтры алерта (нативные, как у RayBot EVM по смыслу)

| Фильтр | Смысл | Рекомендация |
|--------|--------|--------------|
| `max_mcap_alert` | Алерт только если mcap ≤ порога | `15000` |
| `min_mcap_alert` | Опциональный пол mcap (отсечь совсем мёртвые) | пусто / `off` |
| `min_bought_usd` | Минимальная сумма покупки в $; если сумма неизвестна и min задан — алерта нет | по вкусу, напр. `30` |
| `max_bought_usd` | Максимальная сумма покупки в $ | по вкусу или `off` |
| `alert_on_deals` | На каких номерах сделок слать TG | `[2, 3]` |
| `max_deals` | После скольких distinct-токенов кошелёк `done` | `3` |
| `buys_only` | Только входящие токены **с контракта** (DEX/router/pool) | `on` |
| `track_transfers` | Учитывать входящие с EOA (кошелёк→кошелёк). Имеет смысл при `buys_only=off` | `off` |
| `ingest_from_watch` | Писать deal #1 из автопарса | `on` |
| `interval_sec` | Как часто опрашивать watching | `300` |

#### Кнопки и поля вкладки Follow-up

| Элемент UI | Зачем |
|------------|--------|
| Follow-up Вкл | Включает фоновый цикл опроса |
| Ingest | Разрешает автопарсу добавлять кошельки в таблицу |
| Команды бота | Long-poll `/status`, `/filters`, … |
| buys_only / track_transfers | Тип событий, которые считаются «сделкой» |
| Max/Min mcap, Min/Max buy USD | Фильтры алерта |
| Telegram chat / topic | Переопределение `.env` для алертов Follow-up |
| Сохранить | Запись в `followup.json` |
| Запустить сейчас | Внеочередной цикл |
| Стоп | Прервать текущий цикл |
| Проверить Telegram | Тестовое сообщение |
| Сброс счётчиков | Обнулить лог/счётчики статуса (таблица не чистится) |

#### Таблица кошельков — что означают колонки

| Колонка | Смысл |
|---------|--------|
| Адрес | Ссылка на GMGN |
| Статус | `watching` — следим; `done` — набрали `max_deals`; `paused` — зарезервировано |
| Сделок | Сколько distinct-токенов уже учтено |
| Баланс ETH | С автопарса (на момент ingest), может быть пусто |
| Токенов 7д | Сколько разных токенов торговал за 7 дней (на момент ingest) |
| 1-й mcap | Mcap первой сделки (discovery) |
| История | `#N SYMBOL @mcap $buy ✓` — `✓` значит алерт уже отправлен |

#### Команды Telegram-бота (полный список)

Пишите боту в том же чате, что указан в `.env` / Follow-up (иначе команда игнорируется, если chat уже настроен).

| Команда | Пример | Действие |
|---------|--------|----------|
| `/help` `/start` | `/help` | Справка |
| `/status` | `/status` | Вкл/выкл, watching/done, последний цикл |
| `/wallets` | `/wallets` | Краткий список watching |
| `/filters` | `/filters` | Все текущие фильтры |
| `/on` `/off` | `/on` | Вкл/выкл цикл |
| `/run` | `/run` | Запустить цикл сейчас |
| `/set_max_mcap` | `/set_max_mcap 15000` | Max mcap алерта |
| `/set_min_mcap` | `/set_min_mcap 1000` или `off` | Min mcap |
| `/set_min_bought` | `/set_min_bought 50` или `off` | Min buy USD |
| `/set_max_bought` | `/set_max_bought 5000` или `off` | Max buy USD |
| `/set_buys_only` | `/set_buys_only on` | Только DEX buys |
| `/set_transfers` | `/set_transfers off` | EOA transfers |
| `/set_interval` | `/set_interval 300` | Интервал сек (60…86400) |

#### Когда алерт приходит и когда нет

**Приходит**, если одновременно:

- номер сделки 2 или 3 (по умолчанию);
- mcap известен и ≤ `max_mcap_alert` (и ≥ `min_mcap_alert`, если задан);
- сумма покупки проходит min/max buy USD (если фильтры заданы);
- Telegram настроен;
- по этой паре кошелёк+токен ещё не слали алерт.

**Не приходит** (но сделка может быть записана):

- deal #1 (это discovery из автопарса);
- высокий mcap;
- mcap неизвестен (DexScreener не отдал);
- задан `min_bought_usd`, а сумму оценить не удалось;
- `buys_only` отсёк событие (не buy с контракта);
- кошелёк уже `done`.

#### Файлы состояния Follow-up (не коммитить)

| Файл | Назначение |
|------|------------|
| `backend/app/data/followup.db` | SQLite WAL: `wallets` / `deals` / `alert_log` |
| `backend/app/data/followup.json` | конфиг Follow-up |

#### Ограничения Follow-up (важно понимать)

- Deal #1 появляется **только** из автопарса после успешной отправки в Telegram + `ingest_from_watch`.
- Mcap на #2/#3 при poll — **текущий** DexScreener в момент опроса, не исторический в секунду покупки. Если токен уже прокачался до цикла — алерт могут пропустить (сделка всё равно запишется с высоким mcap).
- Опрос смотрит ограниченное число страниц Blockscout (`max_pages=6`); у сверх-активных кошельков редкий старый токен внутри окна можно пропустить.
- Это **EVM-подмножество** фильтров в духе RayBot (buys / transfers / mcap / buy USD), не клон Solana-функций RayBot.

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
Автопарс успел отправить early buyers в Telegram
  → ingest deal #1 (low mcap) → SQLite WAL
  → цикл каждые interval_sec:
       Blockscout token-transfers кошелька
       → buys_only / track_transfers gate
       → новый distinct-токен
       → DexScreener mcap + price → bought_usd
       → record_deal
       → если index 2|3 и фильтры OK → Telegram
       → если mcap высокий → только запись
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

Конфиг Follow-up (`PUT /api/followup`): `enabled`, `interval_sec`, `max_mcap_alert`, `min_mcap_alert`, `min_bought_usd`, `max_bought_usd`, `alert_on_deals` (дефолт `[2,3]`), `max_deals`, `buys_only`, `track_transfers`, chat/topic, `bot_commands_enabled`, `raybot_enabled`, `ingest_from_watch`.

---

## FAQ для рядового пользователя

### Таблица Follow-up пустая

1. Автопарс включён и реально находит early buyers?
2. В Автопарсе проходит **Проверить Telegram** и в логе есть отправка?
3. На Follow-up включён **Ingest** и нажато **Сохранить**?
4. `max_mcap_alert` Follow-up не ниже, чем mcap у найденных buyers (иначе ingest отсекает)?

### Нет алертов на 2-ю/3-ю сделку

1. Follow-up **Вкл** и цикл бежит (`/status` или статус в UI)?
2. У кошелька в истории есть deal `#2` / `#3`?
3. Mcap у новой сделки ≤ `max_mcap_alert`? (высокий mcap = тишина по задумке)
4. Не режет ли `min_bought_usd`, если сумма покупки не оценилась?
5. Telegram chat id верный? Кнопка **Проверить Telegram**.

### Автопарс шлёт 0 кошельков, хотя токены есть

- Слишком жёсткие фильтры 1-й сделки в **Настройках** (баланс / hold / токены 7д).
- Первая on-chain цена уже выше `mcap_threshold` — early buyers пуст.
- RPC 429 — снизьте concurrency / `max_tokens_per_cycle` или поставьте свой `RPC_URL`.

### Бот не отвечает на команды

- `TELEGRAM_BOT_TOKEN` в `.env`, процесс перезапущен.
- На Follow-up включены **Команды бота**.
- Пишете из того же chat id, что в конфиге (иначе команды игнорируются после настройки чата).
- Другой процесс не держит тот же токен (конфликт getUpdates).

### `chat not found` / `401`

Бот не добавлен в чат, неверный токен, или для супергруппы нужен id вида `-100…`.

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
- Follow-up deal #1 зависит от успешного Telegram автопарса; mcap #2/#3 при poll — текущий DexScreener.
- Фильтры Follow-up — EVM-подмножество в духе RayBot (не Solana-функции вроде PumpFun/Jupiter source filters).

---

## Репозитории

- Актуальный снимок **2.2**: [Theseusure/gnomode2.0 @ v2.2.0](https://github.com/Theseusure/gnomode2.0/tree/v2.2.0)
- Зеркало / bunt13: [bunt13/gnomode @ v2.2.0](https://github.com/bunt13/gnomode/tree/v2.2.0)
- Ранний снимок 2.0: [bunt13/gnomode @ v2.0.0](https://github.com/bunt13/gnomode/tree/v2.0.0)
