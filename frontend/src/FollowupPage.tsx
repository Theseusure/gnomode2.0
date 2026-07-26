import { useCallback, useEffect, useState } from 'react'

type FollowupConfig = {
  enabled: boolean
  interval_sec: number
  max_mcap_alert: number
  alert_on_deals: number[]
  max_deals: number
  telegram_chat_id: string
  telegram_topic_id: string
  raybot_enabled: boolean
  ingest_from_watch: boolean
}

type JobLogEntry = {
  ts: number
  stage: string
  message: string
  percent: number
}

type FollowupStatus = {
  enabled: boolean
  running: boolean
  telegram_configured: boolean
  raybot_configured: boolean
  next_run_ts: number | null
  last_run_ts: number | null
  last_run_duration_sec: number | null
  last_error: string | null
  last_message: string
  wallets_watching: number
  wallets_done: number
  last_checked: number
  last_new_deals: number
  last_alerts_sent: number
  stop_requested: boolean
  log: JobLogEntry[]
}

type FollowupDeal = {
  wallet: string
  token: string
  token_symbol: string
  deal_index: number
  mcap_at_buy: number | null
  notified: boolean
}

type FollowupWallet = {
  address: string
  status: string
  deal_count: number
  raybot_synced: boolean
  first_mcap: number | null
  deals: FollowupDeal[]
}

const DEFAULT_CFG: FollowupConfig = {
  enabled: false,
  interval_sec: 300,
  max_mcap_alert: 15000,
  alert_on_deals: [2, 3],
  max_deals: 3,
  telegram_chat_id: '',
  telegram_topic_id: '',
  raybot_enabled: false,
  ingest_from_watch: true,
}

function fmtTs(ts: number | null | undefined): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString()
}

function fmtNum(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default function FollowupPage() {
  const [cfg, setCfg] = useState<FollowupConfig>(DEFAULT_CFG)
  const [status, setStatus] = useState<FollowupStatus | null>(null)
  const [wallets, setWallets] = useState<FollowupWallet[]>([])
  const [saving, setSaving] = useState(false)
  const [flash, setFlash] = useState('')

  const refresh = useCallback(async () => {
    const [c, s, w] = await Promise.all([
      fetch('/api/followup').then((r) => r.json()),
      fetch('/api/followup/status').then((r) => r.json()),
      fetch('/api/followup/wallets?limit=200').then((r) => r.json()),
    ])
    setCfg({ ...DEFAULT_CFG, ...c })
    setStatus(s)
    setWallets(Array.isArray(w) ? w : [])
  }, [])

  useEffect(() => {
    void refresh().catch((e) => setFlash(String(e)))
    const id = window.setInterval(() => {
      void refresh().catch(() => undefined)
    }, 4000)
    return () => window.clearInterval(id)
  }, [refresh])

  const save = async () => {
    setSaving(true)
    setFlash('')
    try {
      const res = await fetch('/api/followup', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      if (!res.ok) throw new Error(await res.text())
      setCfg(await res.json())
      setFlash('Конфиг сохранён')
      await refresh()
    } catch (e) {
      setFlash(String(e))
    } finally {
      setSaving(false)
    }
  }

  const post = async (path: string) => {
    setFlash('')
    try {
      const res = await fetch(path, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setFlash(typeof data.message === 'string' ? data.message : 'OK')
      await refresh()
    } catch (e) {
      setFlash(String(e))
    }
  }

  return (
    <>
      <header className="hero">
        <p className="brand">gnomode</p>
        <h1>Follow-up кошельков</h1>
        <p className="lede">
          Первая сделка на низком mcap → таблица → алерт на 2-й/3-й новый токен
          только при низком mcap. Высокий mcap — без уведомления. Опционально
          RayBot (EVM) с фильтром MC.
        </p>
      </header>

      <section className="panel meta-panel watch-status">
        <div className="watch-status-grid">
          <div>
            <span className="muted">Статус</span>
            <div>{status?.running ? 'цикл' : cfg.enabled ? 'ожидание' : 'выкл'}</div>
          </div>
          <div>
            <span className="muted">Watching / done</span>
            <div>
              {status?.wallets_watching ?? 0} / {status?.wallets_done ?? 0}
            </div>
          </div>
          <div>
            <span className="muted">Telegram / RayBot</span>
            <div>
              {status?.telegram_configured ? 'TG ok' : 'TG —'} ·{' '}
              {status?.raybot_configured ? 'Ray ok' : 'Ray —'}
            </div>
          </div>
          <div>
            <span className="muted">Последний / следующий</span>
            <div className="muted tiny">
              {fmtTs(status?.last_run_ts)} → {fmtTs(status?.next_run_ts)}
            </div>
          </div>
        </div>
        {status?.last_message ? <p className="watch-msg">{status.last_message}</p> : null}
        {status?.last_error ? <p className="watch-error">{status.last_error}</p> : null}
        {flash ? <p className="muted">{flash}</p> : null}
      </section>

      <section className="panel input-panel">
        <h2 className="section-title">Расписание и фильтры</h2>
        <div className="row">
          <label className="field check-field">
            <span className="muted">Follow-up</span>
            <label className="check-inline">
              <input
                type="checkbox"
                checked={cfg.enabled}
                onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })}
              />
              Вкл
            </label>
          </label>
          <label className="field check-field">
            <span className="muted">Автопарс → таблица</span>
            <label className="check-inline">
              <input
                type="checkbox"
                checked={cfg.ingest_from_watch}
                onChange={(e) =>
                  setCfg({ ...cfg, ingest_from_watch: e.target.checked })
                }
              />
              Ingest
            </label>
          </label>
          <label className="field check-field">
            <span className="muted">RayBot</span>
            <label className="check-inline">
              <input
                type="checkbox"
                checked={cfg.raybot_enabled}
                onChange={(e) =>
                  setCfg({ ...cfg, raybot_enabled: e.target.checked })
                }
              />
              Sync EVM
            </label>
          </label>
          <label className="field compact">
            <span className="muted">Интервал, сек</span>
            <input
              type="number"
              value={cfg.interval_sec}
              min={60}
              onChange={(e) =>
                setCfg({ ...cfg, interval_sec: Number(e.target.value) || 300 })
              }
            />
          </label>
          <label className="field compact">
            <span className="muted">Max mcap алерта, $</span>
            <input
              type="number"
              value={cfg.max_mcap_alert}
              min={0}
              onChange={(e) =>
                setCfg({
                  ...cfg,
                  max_mcap_alert: Number(e.target.value) || 0,
                })
              }
            />
          </label>
          <label className="field compact">
            <span className="muted">Max сделок</span>
            <input
              type="number"
              value={cfg.max_deals}
              min={1}
              max={20}
              onChange={(e) =>
                setCfg({ ...cfg, max_deals: Number(e.target.value) || 3 })
              }
            />
          </label>
          <label className="field">
            <span className="muted">Telegram chat id</span>
            <input
              value={cfg.telegram_chat_id}
              onChange={(e) =>
                setCfg({ ...cfg, telegram_chat_id: e.target.value })
              }
              placeholder="пусто = .env"
            />
          </label>
          <label className="field compact">
            <span className="muted">Topic id</span>
            <input
              value={cfg.telegram_topic_id}
              onChange={(e) =>
                setCfg({ ...cfg, telegram_topic_id: e.target.value })
              }
            />
          </label>
        </div>
        <div className="row">
          <button
            type="button"
            className={`primary${saving ? ' busy' : ''}`}
            disabled={saving}
            onClick={() => void save()}
          >
            Сохранить
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => void post('/api/followup/run')}
            disabled={!!status?.running}
          >
            Запустить сейчас
          </button>
          <button
            type="button"
            className="ghost danger"
            onClick={() => void post('/api/followup/stop')}
          >
            Стоп
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => void post('/api/followup/test-telegram')}
          >
            Проверить Telegram
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => void post('/api/followup/test-raybot')}
          >
            Проверить RayBot
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => void post('/api/followup/reset-counters')}
          >
            Сброс счётчиков
          </button>
        </div>
      </section>

      <section className="panel">
        <h2 className="section-title">Лог</h2>
        <div className="log-box">
          {(status?.log ?? []).slice(-50).map((e, i) => (
            <div key={`${e.ts}-${i}`} className="log-line">
              <span className="muted">{fmtTs(e.ts)}</span> [{e.stage}] {e.message}
            </div>
          ))}
          {!status?.log?.length ? <p className="muted">Пока пусто</p> : null}
        </div>
      </section>

      <section className="panel">
        <h2 className="section-title">Таблица ({wallets.length})</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Адрес</th>
                <th>Статус</th>
                <th>Сделок</th>
                <th>1-й mcap</th>
                <th>RayBot</th>
                <th>История</th>
              </tr>
            </thead>
            <tbody>
              {wallets.map((w) => (
                <tr key={w.address}>
                  <td>
                    <a
                      href={`https://gmgn.ai/robinhood/address/${w.address}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <code>
                        {w.address.slice(0, 6)}…{w.address.slice(-4)}
                      </code>
                    </a>
                  </td>
                  <td>{w.status}</td>
                  <td>{w.deal_count}</td>
                  <td>{fmtNum(w.first_mcap)}</td>
                  <td>{w.raybot_synced ? 'yes' : '—'}</td>
                  <td className="muted tiny">
                    {w.deals
                      .map(
                        (d) =>
                          `#${d.deal_index} ${d.token_symbol || d.token.slice(0, 6)} @${fmtNum(d.mcap_at_buy)}${d.notified ? ' ✓' : ''}`,
                      )
                      .join(' · ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!wallets.length ? (
            <p className="muted">Нет кошельков — включите ingest из автопарса.</p>
          ) : null}
        </div>
      </section>
    </>
  )
}
