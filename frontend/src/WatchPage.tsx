import { useCallback, useEffect, useState } from 'react'

type ScreenSortBy = 'liquidity' | 'market_cap' | 'traders' | 'pair_age'
type ScreenSortOrder = 'asc' | 'desc'

type WatchConfig = {
  enabled: boolean
  interval_sec: number
  max_tokens_per_cycle: number
  telegram_chat_id: string
  telegram_topic_id?: string
  gnome_banter_enabled?: boolean
  screen: {
    min_liq: number | null
    max_liq: number | null
    min_mcap: number | null
    max_mcap: number | null
    min_ath_mcap?: number | null
    min_traders: number | null
    max_traders: number | null
    min_pair_age_hours: number | null
    max_pair_age_hours: number | null
    exclude_honeypots: boolean
    sort_by: ScreenSortBy
    sort_order: ScreenSortOrder
    max_results: number
  }
  wallet: {
    mcap_threshold: number | null
    exclude_honeypots: boolean
    min_wallet_balance_eth: number | null
    max_wallet_balance_eth: number | null
    min_hold_time_minutes: number | null
    max_hold_time_minutes: number | null
    min_tokens_traded_7d: number | null
    max_tokens_traded_7d: number | null
  }
}

type JobLogEntry = {
  ts: number
  stage: string
  message: string
  percent: number
  token?: string | null
}

type WatchStatus = {
  enabled: boolean
  running: boolean
  telegram_configured: boolean
  next_run_ts: number | null
  last_run_ts: number | null
  last_run_duration_sec: number | null
  last_error: string | null
  last_message: string
  last_tokens_screened: number
  last_tokens_parsed: number
  last_tokens_held?: number
  last_tokens_qualified?: number
  last_buyers_found: number
  last_buyers_new: number
  last_buyers_sent: number
  last_buyers_skipped: number
  seen_count: number
  hold_count?: number
  parsed_token_count?: number
  needs_catchup?: boolean
  catchup_lookback_hours?: number | null
  is_catchup_run?: boolean
  gnome_banter_enabled?: boolean
  gnome_banter_next_ts?: number | null
  stop_requested?: boolean
  log?: JobLogEntry[]
}

function fmtLogTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

async function readApiError(res: Response, fallback: string) {
  try {
    const data = (await res.json()) as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: string }).msg) : String(d)))
        .join('; ')
    }
  } catch {
    /* ignore */
  }
  return `${fallback} (${res.status})`
}

function fmtLookback(hours: number | null | undefined) {
  if (hours == null || !Number.isFinite(hours)) return '—'
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} мин`
  if (Math.abs(hours - 24) < 0.05) return '24 ч'
  return `${hours.toFixed(1)} ч`
}

const DEFAULT_INTERVAL_MIN = '15'
const DEFAULT_MAX_TOKENS = '20'

function fmtTs(ts: number | null) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('ru-RU')
}

function fmtAgo(ts: number | null) {
  if (!ts) return 'никогда'
  const secs = Math.max(0, Date.now() / 1000 - ts)
  if (secs < 60) return `${Math.round(secs)}с назад`
  if (secs < 3600) return `${Math.round(secs / 60)}м назад`
  return `${Math.round(secs / 3600)}ч назад`
}

function fmtIn(ts: number | null) {
  if (!ts) return '—'
  const secs = Math.max(0, ts - Date.now() / 1000)
  if (secs < 60) return `через ${Math.round(secs)}с`
  if (secs < 3600) return `через ${Math.round(secs / 60)}м`
  return `через ${Math.round(secs / 3600)}ч`
}

function configToForms(cfg: WatchConfig): {
  enabled: boolean
  intervalMin: string
  maxTokens: string
  chatId: string
  topicId: string
  gnomeBanter: boolean
} {
  return {
    enabled: cfg.enabled,
    intervalMin: String(Math.max(1, Math.round(cfg.interval_sec / 60))),
    maxTokens: String(cfg.max_tokens_per_cycle),
    chatId: cfg.telegram_chat_id || '',
    topicId: cfg.telegram_topic_id || '',
    gnomeBanter: cfg.gnome_banter_enabled !== false,
  }
}

export default function WatchPage() {
  const [enabled, setEnabled] = useState(false)
  const [intervalMin, setIntervalMin] = useState(DEFAULT_INTERVAL_MIN)
  const [maxTokens, setMaxTokens] = useState(DEFAULT_MAX_TOKENS)
  const [chatId, setChatId] = useState('')
  const [topicId, setTopicId] = useState('')
  const [gnomeBanter, setGnomeBanter] = useState(true)
  const [status, setStatus] = useState<WatchStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [actionMsg, setActionMsg] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [cfgRes, stRes] = await Promise.all([
        fetch('/api/watch'),
        fetch('/api/watch/status'),
      ])
      if (!cfgRes.ok) throw new Error(`Конфиг: ошибка ${cfgRes.status}`)
      if (!stRes.ok) throw new Error(`Статус: ошибка ${stRes.status}`)
      const cfg = (await cfgRes.json()) as WatchConfig
      const st = (await stRes.json()) as WatchStatus
      const forms = configToForms(cfg)
      setEnabled(forms.enabled)
      setIntervalMin(forms.intervalMin)
      setMaxTokens(forms.maxTokens)
      setChatId(forms.chatId)
      setTopicId(forms.topicId)
      setGnomeBanter(forms.gnomeBanter)
      setStatus(st)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const id = window.setInterval(() => {
      void fetch('/api/watch/status')
        .then((r) => (r.ok ? r.json() : null))
        .then((st) => {
          if (st) setStatus(st as WatchStatus)
        })
        .catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(id)
  }, [])

  const buildSchedulePayload = useCallback(async (): Promise<WatchConfig> => {
    const curRes = await fetch('/api/watch')
    if (!curRes.ok) throw new Error(await readApiError(curRes, 'Чтение конфига'))
    const current = (await curRes.json()) as WatchConfig
    const mins = Math.max(1, Number(intervalMin) || 15)
    const maxTok = Math.min(2000, Math.max(1, Number(maxTokens) || 20))
    return {
      ...current,
      enabled,
      interval_sec: mins * 60,
      max_tokens_per_cycle: maxTok,
      telegram_chat_id: chatId.trim(),
      telegram_topic_id: topicId.trim(),
      gnome_banter_enabled: gnomeBanter,
    }
  }, [enabled, intervalMin, maxTokens, chatId, topicId, gnomeBanter])

  const save = useCallback(async () => {
    setSaving(true)
    setActionMsg('')
    setError('')
    try {
      const payload = await buildSchedulePayload()
      const res = await fetch('/api/watch', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await readApiError(res, 'Не удалось сохранить'))
      const cfg = (await res.json()) as WatchConfig
      const forms = configToForms(cfg)
      setEnabled(forms.enabled)
      setIntervalMin(forms.intervalMin)
      setMaxTokens(forms.maxTokens)
      setChatId(forms.chatId)
      setTopicId(forms.topicId)
      setGnomeBanter(forms.gnomeBanter)
      setActionMsg('Сохранено (фильтры — во вкладке Настройки)')
      const st = await fetch('/api/watch/status')
      if (st.ok) setStatus((await st.json()) as WatchStatus)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }, [buildSchedulePayload])

  const runNow = useCallback(async () => {
    setActionMsg('')
    setError('')
    try {
      const payload = await buildSchedulePayload()
      const saveRes = await fetch('/api/watch', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!saveRes.ok) throw new Error(await readApiError(saveRes, 'Не удалось сохранить'))
      const res = await fetch('/api/watch/run', { method: 'POST' })
      if (!res.ok) throw new Error(await readApiError(res, 'Не удалось запустить'))
      setStatus((await res.json()) as WatchStatus)
      setActionMsg('Цикл запущен')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [buildSchedulePayload])

  const stopNow = useCallback(async () => {
    setActionMsg('')
    setError('')
    try {
      const res = await fetch('/api/watch/stop', { method: 'POST' })
      if (!res.ok) throw new Error(await readApiError(res, 'Не удалось остановить'))
      setStatus((await res.json()) as WatchStatus)
      setActionMsg('Остановка запрошена')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const clearSeen = useCallback(async () => {
    if (
      !window.confirm(
        'Очистить историю дедупа? Ранее отправленные пары кошелёк+токен снова могут попасть в алерты.',
      )
    ) {
      return
    }
    try {
      const res = await fetch('/api/watch/clear-seen', { method: 'POST' })
      if (!res.ok) throw new Error(await readApiError(res, 'Не удалось очистить'))
      setActionMsg('История дедупа очищена')
      const st = await fetch('/api/watch/status')
      if (st.ok) setStatus((await st.json()) as WatchStatus)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const resetCounters = useCallback(async () => {
    setActionMsg('')
    setError('')
    try {
      const res = await fetch('/api/watch/reset-counters', { method: 'POST' })
      if (!res.ok) throw new Error(await readApiError(res, 'Не удалось сбросить'))
      setStatus((await res.json()) as WatchStatus)
      setActionMsg('Счётчики сброшены')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const testTelegram = useCallback(async () => {
    setActionMsg('')
    setError('')
    try {
      // Persist schedule/Telegram first so chat/topic fields are what we test.
      const payload = await buildSchedulePayload()
      const saveRes = await fetch('/api/watch', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!saveRes.ok) throw new Error(await readApiError(saveRes, 'Не удалось сохранить'))
      const res = await fetch('/api/watch/test-telegram', { method: 'POST' })
      if (!res.ok) throw new Error(await readApiError(res, 'Telegram недоступен'))
      const data = (await res.json()) as {
        message?: string
        bot_username?: string
        topic_id?: number | null
      }
      const who = data.bot_username ? `@${data.bot_username}` : 'бот'
      const topic = data.topic_id != null ? ` · топик ${data.topic_id}` : ''
      setActionMsg(data.message || `OK: ${who}${topic}`)
      const st = await fetch('/api/watch/status')
      if (st.ok) setStatus((await st.json()) as WatchStatus)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [buildSchedulePayload])

  if (loading) {
    return (
      <>
        <header className="hero">
          <p className="brand">gnomode</p>
          <h1>Автопарс</h1>
          <p className="lede">Загрузка…</p>
        </header>
      </>
    )
  }

  return (
    <>
      <header className="hero">
        <p className="brand">gnomode</p>
        <h1>Автопарс и алерты в Telegram</h1>
        <p className="lede">
          По расписанию скринит токены, паркует ранние в hold до ATH mcap, затем парсит
          ранних покупателей по фильтрам кошельков и шлёт новые пары кошелёк+токен в Telegram.
        </p>
      </header>

      <section className="panel meta-panel watch-status">
        <div className="watch-status-grid">
          <div>
            <span className="muted">Статус</span>
            <strong>
              {status?.running ? 'Выполняется' : status?.enabled ? 'Включён' : 'Выключен'}
            </strong>
          </div>
          <div>
            <span className="muted">Telegram</span>
            <strong>{status?.telegram_configured ? 'Настроен' : 'Не настроен'}</strong>
          </div>
          <div>
            <span className="muted">Последний запуск</span>
            <strong>{fmtAgo(status?.last_run_ts ?? null)}</strong>
            <div className="muted tiny">{fmtTs(status?.last_run_ts ?? null)}</div>
          </div>
          <div>
            <span className="muted">Следующий запуск</span>
            <strong>{status?.enabled ? fmtIn(status?.next_run_ts ?? null) : '—'}</strong>
          </div>
          <div>
            <span className="muted">Последний цикл</span>
            <strong>
              {status
                ? `${status.last_tokens_parsed} ток · ${status.last_buyers_sent} отпр. · ${status.last_buyers_skipped} проп.`
                : '—'}
            </strong>
            {status ? (
              <div className="muted tiny">
                qualify {status.last_tokens_qualified ?? 0} · hold цикл{' '}
                {status.last_tokens_held ?? 0}
              </div>
            ) : null}
          </div>
          <div>
            <span className="muted">Hold / спарсено</span>
            <strong>
              {status?.hold_count ?? 0} / {status?.parsed_token_count ?? 0}
            </strong>
          </div>
          <div>
            <span className="muted">Уже отправлено</span>
            <strong>{status?.seen_count ?? 0}</strong>
          </div>
          <div>
            <span className="muted">Догон</span>
            <strong>
              {status?.is_catchup_run
                ? `сейчас · ${fmtLookback(status.catchup_lookback_hours)}`
                : status?.needs_catchup
                  ? `ожидает · ${fmtLookback(status.catchup_lookback_hours)}`
                  : 'не нужен'}
            </strong>
          </div>
          <div>
            <span className="muted">Гном в чате</span>
            <strong>
              {status?.gnome_banter_enabled === false
                ? 'выкл'
                : status?.enabled
                  ? status?.gnome_banter_next_ts
                    ? fmtIn(status.gnome_banter_next_ts)
                    : 'ждёт'
                  : 'когда автопарс вкл'}
            </strong>
          </div>
        </div>
        {status?.last_message ? (
          <p className="watch-msg">{status.last_message}</p>
        ) : null}
        {status?.last_error ? <p className="watch-error">{status.last_error}</p> : null}
        {!status?.telegram_configured ? (
          <p className="muted">
            Укажите <code>TELEGRAM_BOT_TOKEN</code> в <code>.env</code> и chat id ниже (или{' '}
            <code>TELEGRAM_CHAT_ID</code>).
          </p>
        ) : null}
      </section>

      <section className="panel input-panel">
        <h2 className="section-title">Расписание</h2>
        <div className="row">
          <label className="field check-field">
            <span>Включено</span>
            <label className="check-inline">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              Запускать по интервалу
            </label>
          </label>
          <label className="field compact">
            <span>Интервал (минуты)</span>
            <input
              type="number"
              min={1}
              max={1440}
              value={intervalMin}
              onChange={(e) => setIntervalMin(e.target.value)}
            />
          </label>
          <label className="field compact">
            <span>Макс. токенов / цикл</span>
            <input
              type="number"
              min={1}
              max={2000}
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Telegram chat id</span>
            <input
              type="text"
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              placeholder="из .env, если пусто"
              spellCheck={false}
            />
          </label>
          <label className="field compact">
            <span>Topic id (топик)</span>
            <input
              type="text"
              value={topicId}
              onChange={(e) => setTopicId(e.target.value)}
              placeholder="из .env / пусто"
              spellCheck={false}
            />
          </label>
          <label className="field check-field">
            <span>Гном</span>
            <label className="check-inline">
              <input
                type="checkbox"
                checked={gnomeBanter}
                onChange={(e) => setGnomeBanter(e.target.checked)}
              />
              Жалобы в TG каждые 10–15 мин
            </label>
          </label>
        </div>
        <div className="row">
          <button type="button" className={`primary${saving ? ' busy' : ''}`} disabled={saving} onClick={save}>
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
          <button type="button" className="ghost" onClick={runNow} disabled={!!status?.running}>
            {status?.running ? 'Выполняется…' : 'Запустить сейчас'}
          </button>
          <button
            type="button"
            className="ghost danger"
            onClick={stopNow}
            disabled={!status?.running && !status?.stop_requested}
          >
            {status?.stop_requested ? 'Останавливается…' : 'Принудительный стоп'}
          </button>
          <button type="button" className="ghost" onClick={resetCounters}>
            Сброс счётчиков
          </button>
          <button type="button" className="ghost" onClick={testTelegram}>
            Проверить Telegram
          </button>
          <button type="button" className="ghost" onClick={clearSeen}>
            Очистить дедуп
          </button>
          {actionMsg ? <span className="muted">{actionMsg}</span> : null}
        </div>
        {error ? <p className="watch-error">{error}</p> : null}
      </section>

      <section className="panel meta-panel">
        <div className="job-log" aria-live="polite">
          <div className="job-log-head">
            <h2 className="section-title">Лог автопарса</h2>
            <span className="muted">
              {status?.log?.length ? `${status.log.length} записей` : 'пока пусто'}
            </span>
          </div>
          <ol className="job-log-list">
            {(status?.log ?? []).slice().reverse().map((entry, i) => (
              <li key={`${entry.ts}-${entry.stage}-${i}`} className="job-log-row">
                <time dateTime={new Date(entry.ts * 1000).toISOString()}>
                  {fmtLogTime(entry.ts)}
                </time>
                <span className={`job-log-stage stage-${entry.stage}`}>{entry.stage}</span>
                <span className="job-log-msg" title={entry.message}>
                  {entry.message}
                </span>
                <span className="job-log-pct">{Number.isFinite(entry.percent) ? `${Math.round(entry.percent)}%` : ''}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="panel input-panel">
        <h2 className="section-title">Фильтры</h2>
        <p className="lede" style={{ margin: 0 }}>
          Фильтры токена и первой сделки кошелька вынесены во вкладку{' '}
          <b>Настройки</b>. Здесь — только расписание, Telegram и лог автопарса.
        </p>
      </section>
    </>
  )
}
