import { useCallback, useEffect, useState } from 'react'

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
  last_message: string
  last_error: string | null
  last_tokens_screened: number
  last_tokens_parsed: number
  last_buyers_found: number
  last_buyers_sent: number
  last_buyers_skipped: number
  seen_count: number
  log?: JobLogEntry[]
}

type FollowupStatus = {
  enabled: boolean
  running: boolean
  telegram_configured: boolean
  next_run_ts: number | null
  last_run_ts: number | null
  last_message: string
  last_error: string | null
  wallets_watching: number
  wallets_done: number
  last_checked: number
  last_new_deals: number
  last_alerts_sent: number
  log?: JobLogEntry[]
}

type FollowupDeal = {
  wallet: string
  token: string
  token_symbol: string
  deal_index: number
  mcap_at_buy: number | null
  bought_usd: number | null
  notified: boolean
}

type FollowupWallet = {
  address: string
  status: string
  deal_count: number
  first_mcap: number | null
  tokens_traded_7d: number | null
  deals: FollowupDeal[]
}

type HvatStatus = {
  mcap_cap: number
  watch: WatchStatus
  followup: FollowupStatus
  profile: {
    one_trade: boolean
    max_tokens_traded_7d: number
    first_buy_max_mcap: number
    alert_deals: number[]
    alert_max_mcap: number
  }
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

function fmtLogTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export default function HvatPage() {
  const [st, setSt] = useState<HvatStatus | null>(null)
  const [wallets, setWallets] = useState<FollowupWallet[]>([])
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState('')

  const refresh = useCallback(async () => {
    const [h, w] = await Promise.all([
      fetch('/api/hvat/status').then((r) => r.json()),
      fetch('/api/followup/wallets?status=watching&limit=100').then((r) => r.json()),
    ])
    setSt(h)
    setWallets(Array.isArray(w) ? w : [])
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => void refresh(), 4000)
    return () => window.clearInterval(id)
  }, [refresh])

  async function post(path: string, okMsg: string) {
    setBusy(true)
    setFlash('')
    try {
      const res = await fetch(path, { method: 'POST' })
      if (!res.ok) throw new Error(`${res.status}`)
      setFlash(okMsg)
      await refresh()
    } catch (e) {
      setFlash(e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  const watch = st?.watch
  const follow = st?.followup
  const active = Boolean(watch?.enabled && follow?.enabled)
  const logs = [
    ...(watch?.log ?? []).slice(-8).map((x) => ({ ...x, src: 'парс' })),
    ...(follow?.log ?? []).slice(-8).map((x) => ({ ...x, src: 'след' })),
  ]
    .sort((a, b) => a.ts - b.ts)
    .slice(-14)

  return (
    <section className="panel hvat-panel">
      <header className="hvat-hero">
        <h1 className="hvat-title">Хвать</h1>
        <p className="lede">
          Токены из индекса → кошельки с одной сделкой (первая покупка ≤{' '}
          {fmtNum(st?.mcap_cap ?? 20_000)}$) → алерты на сделки #2/#3 на низкой mcap.
        </p>
      </header>

      <div className="row gap actions">
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={() => void post('/api/hvat/enable', 'Хвать включён')}
        >
          Включить профиль
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void post('/api/hvat/run', 'Цикл запущен')}
        >
          Запустить сейчас
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void post('/api/hvat/disable', 'Хвать выключен')}
        >
          Выключить
        </button>
        {flash ? <span className="muted">{flash}</span> : null}
      </div>

      <div className="stat-grid hvat-stats">
        <div>
          <div className="muted">Статус</div>
          <strong>{active ? 'активен' : 'выкл'}</strong>
        </div>
        <div>
          <div className="muted">Парс</div>
          <strong>
            {watch?.running ? 'идёт' : watch?.enabled ? 'ожидание' : 'выкл'}
          </strong>
        </div>
        <div>
          <div className="muted">След. сделки</div>
          <strong>
            {follow?.running ? 'идёт' : follow?.enabled ? 'ожидание' : 'выкл'}
          </strong>
        </div>
        <div>
          <div className="muted">В слежке</div>
          <strong>{follow?.wallets_watching ?? 0}</strong>
        </div>
        <div>
          <div className="muted">Найдено / отпр.</div>
          <strong>
            {watch?.last_buyers_found ?? 0} / {watch?.last_buyers_sent ?? 0}
          </strong>
        </div>
        <div>
          <div className="muted">Алерты #2/#3</div>
          <strong>{follow?.last_alerts_sent ?? 0}</strong>
        </div>
      </div>

      <p className="muted hvat-meta">
        Профиль: 1 токен за 7д · buys=1 · mcap ≤ {fmtNum(st?.profile.first_buy_max_mcap)} ·
        алерты deals {(st?.profile.alert_deals ?? [2, 3]).join(', ')} ≤{' '}
        {fmtNum(st?.profile.alert_max_mcap)}
        <br />
        Парс: {watch?.last_message || '—'} · след. {fmtTs(watch?.next_run_ts)}
        <br />
        Follow-up: {follow?.last_message || '—'} · след. {fmtTs(follow?.next_run_ts)}
      </p>
      {(watch?.last_error || follow?.last_error) && (
        <p className="error">
          {watch?.last_error || follow?.last_error}
        </p>
      )}

      <h2 className="section-title">Кошельки в слежке</h2>
      {wallets.length === 0 ? (
        <p className="empty">Пока пусто — включи Хвать и дождись автопарса.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Кошелёк</th>
                <th>Сделок</th>
                <th>1-я mcap</th>
                <th>7д токенов</th>
                <th>Последние deals</th>
              </tr>
            </thead>
            <tbody>
              {wallets.map((w) => (
                <tr key={w.address}>
                  <td className="mono">{w.address.slice(0, 10)}…</td>
                  <td>{w.deal_count}</td>
                  <td>{fmtNum(w.first_mcap)}</td>
                  <td>{w.tokens_traded_7d ?? '—'}</td>
                  <td>
                    {(w.deals ?? [])
                      .slice(-3)
                      .map(
                        (d) =>
                          `#${d.deal_index} ${d.token_symbol || d.token.slice(0, 6)} @${fmtNum(d.mcap_at_buy)}${d.notified ? '✓' : ''}`,
                      )
                      .join(' · ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="section-title">Лог</h2>
      <ul className="job-log">
        {logs.length === 0 ? (
          <li className="muted">Нет записей</li>
        ) : (
          logs.map((x, i) => (
            <li key={`${x.ts}-${i}`}>
              <span className="muted">{fmtLogTime(x.ts)}</span>{' '}
              <span className="muted">[{x.src}]</span> {x.message}
            </li>
          ))
        )}
      </ul>
    </section>
  )
}
