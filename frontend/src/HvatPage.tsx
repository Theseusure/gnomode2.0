import { useCallback, useEffect, useState } from 'react'

type ScreenSortBy = 'liquidity' | 'market_cap' | 'traders' | 'pair_age'
type ScreenSortOrder = 'asc' | 'desc'
type TokensUniquePeriod = '12h' | '24h' | '1d' | '3d' | '7d' | '30d'

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

type ScreenForm = {
  min_liq: string
  max_liq: string
  min_mcap: string
  max_mcap: string
  min_ath_mcap: string
  min_traders: string
  max_traders: string
  min_pair_age_hours: string
  max_pair_age_hours: string
  sort_by: ScreenSortBy
  sort_order: ScreenSortOrder
  max_results: string
  exclude_honeypots: boolean
}

type WalletForm = {
  mcap_threshold: string
  exclude_honeypots: boolean
  min_wallet_balance_eth: string
  max_wallet_balance_eth: string
  min_hold_time_minutes: string
  max_hold_time_minutes: string
  min_tokens_traded_7d: string
  max_tokens_traded_7d: string
  tokens_unique_period: TokensUniquePeriod
}

type WatchConfig = {
  enabled: boolean
  interval_sec: number
  max_tokens_per_cycle: number
  screen: {
    min_liq: number | null
    max_liq: number | null
    min_mcap: number | null
    max_mcap: number | null
    min_ath_mcap: number | null
    min_traders: number | null
    max_traders: number | null
    min_pair_age_hours: number | null
    max_pair_age_hours: number | null
    sort_by: ScreenSortBy
    sort_order: ScreenSortOrder
    max_results: number
    exclude_honeypots: boolean
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
    tokens_unique_period?: TokensUniquePeriod
  }
}

type HvatStatus = {
  mcap_cap: number
  watch: WatchStatus
  followup: FollowupStatus
  config?: WatchConfig
  profile: {
    one_trade: boolean
    max_tokens_traded_7d: number | null
    min_tokens_traded_7d?: number | null
    tokens_unique_period?: TokensUniquePeriod
    first_buy_max_mcap: number | null
    alert_deals: number[]
    alert_max_mcap: number
  }
}

const PERIODS: TokensUniquePeriod[] = ['12h', '24h', '1d', '3d', '7d', '30d']

const DEFAULT_SCREEN: ScreenForm = {
  min_liq: '',
  max_liq: '',
  min_mcap: '',
  max_mcap: '',
  min_ath_mcap: '50000',
  min_traders: '',
  max_traders: '',
  min_pair_age_hours: '',
  max_pair_age_hours: '',
  sort_by: 'liquidity',
  sort_order: 'desc',
  max_results: '500',
  exclude_honeypots: true,
}

const DEFAULT_WALLET: WalletForm = {
  mcap_threshold: '20000',
  exclude_honeypots: true,
  min_wallet_balance_eth: '',
  max_wallet_balance_eth: '',
  min_hold_time_minutes: '',
  max_hold_time_minutes: '',
  min_tokens_traded_7d: '1',
  max_tokens_traded_7d: '1',
  tokens_unique_period: '7d',
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

function parseOpt(raw: string): number | null {
  const t = raw.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function numToStr(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return ''
  return String(n)
}

function cfgToScreen(cfg: WatchConfig): ScreenForm {
  return {
    ...DEFAULT_SCREEN,
    min_liq: numToStr(cfg.screen.min_liq),
    max_liq: numToStr(cfg.screen.max_liq),
    min_mcap: numToStr(cfg.screen.min_mcap),
    max_mcap: numToStr(cfg.screen.max_mcap),
    min_ath_mcap: numToStr(cfg.screen.min_ath_mcap) || '50000',
    min_traders: numToStr(cfg.screen.min_traders),
    max_traders: numToStr(cfg.screen.max_traders),
    min_pair_age_hours: numToStr(cfg.screen.min_pair_age_hours),
    max_pair_age_hours: numToStr(cfg.screen.max_pair_age_hours),
    sort_by: cfg.screen.sort_by || 'liquidity',
    sort_order: cfg.screen.sort_order || 'desc',
    max_results: String(cfg.screen.max_results || 500),
    exclude_honeypots: cfg.screen.exclude_honeypots !== false,
  }
}

function cfgToWallet(cfg: WatchConfig): WalletForm {
  const period = cfg.wallet.tokens_unique_period
  return {
    ...DEFAULT_WALLET,
    mcap_threshold: numToStr(cfg.wallet.mcap_threshold) || '20000',
    exclude_honeypots: cfg.wallet.exclude_honeypots !== false,
    min_wallet_balance_eth: numToStr(cfg.wallet.min_wallet_balance_eth),
    max_wallet_balance_eth: numToStr(cfg.wallet.max_wallet_balance_eth),
    min_hold_time_minutes: numToStr(cfg.wallet.min_hold_time_minutes),
    max_hold_time_minutes: numToStr(cfg.wallet.max_hold_time_minutes),
    min_tokens_traded_7d: numToStr(cfg.wallet.min_tokens_traded_7d) || '1',
    max_tokens_traded_7d: numToStr(cfg.wallet.max_tokens_traded_7d) || '1',
    tokens_unique_period: PERIODS.includes(period as TokensUniquePeriod)
      ? (period as TokensUniquePeriod)
      : '7d',
  }
}

export default function HvatPage() {
  const [st, setSt] = useState<HvatStatus | null>(null)
  const [wallets, setWallets] = useState<FollowupWallet[]>([])
  const [screen, setScreen] = useState<ScreenForm>(DEFAULT_SCREEN)
  const [wallet, setWallet] = useState<WalletForm>(DEFAULT_WALLET)
  const [maxTokensCycle, setMaxTokensCycle] = useState('20')
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState('')

  const refresh = useCallback(async () => {
    const [h, w] = await Promise.all([
      fetch('/api/hvat/status').then((r) => r.json() as Promise<HvatStatus>),
      fetch('/api/followup/wallets?status=watching&limit=100').then((r) => r.json()),
    ])
    setSt(h)
    setWallets(Array.isArray(w) ? w : [])
    if (h.config) {
      setScreen(cfgToScreen(h.config))
      setWallet(cfgToWallet(h.config))
      setMaxTokensCycle(String(h.config.max_tokens_per_cycle || 20))
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => {
      // Soft status poll — don't clobber in-progress filter edits every tick.
      void (async () => {
        try {
          const [h, w] = await Promise.all([
            fetch('/api/hvat/status').then((r) => r.json() as Promise<HvatStatus>),
            fetch('/api/followup/wallets?status=watching&limit=100').then((r) => r.json()),
          ])
          setSt(h)
          setWallets(Array.isArray(w) ? w : [])
        } catch {
          /* ignore */
        }
      })()
    }, 5000)
    return () => window.clearInterval(id)
  }, [refresh])

  const setScreenField = <K extends keyof ScreenForm>(key: K, value: ScreenForm[K]) =>
    setScreen((prev) => ({ ...prev, [key]: value }))
  const setWalletField = <K extends keyof WalletForm>(key: K, value: WalletForm[K]) =>
    setWallet((prev) => ({ ...prev, [key]: value }))

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

  async function saveFilters() {
    setBusy(true)
    setFlash('')
    try {
      const body = {
        max_tokens_per_cycle: parseOpt(maxTokensCycle) ?? 20,
        sync_followup_mcap: true,
        screen: {
          min_liq: parseOpt(screen.min_liq),
          max_liq: parseOpt(screen.max_liq),
          min_mcap: parseOpt(screen.min_mcap),
          max_mcap: parseOpt(screen.max_mcap),
          min_ath_mcap: parseOpt(screen.min_ath_mcap),
          min_traders: parseOpt(screen.min_traders),
          max_traders: parseOpt(screen.max_traders),
          min_pair_age_hours: parseOpt(screen.min_pair_age_hours),
          max_pair_age_hours: parseOpt(screen.max_pair_age_hours),
          sort_by: screen.sort_by,
          sort_order: screen.sort_order,
          max_results: parseOpt(screen.max_results) ?? 500,
          exclude_honeypots: screen.exclude_honeypots,
        },
        wallet: {
          mcap_threshold: parseOpt(wallet.mcap_threshold),
          exclude_honeypots: wallet.exclude_honeypots,
          min_wallet_balance_eth: parseOpt(wallet.min_wallet_balance_eth),
          max_wallet_balance_eth: parseOpt(wallet.max_wallet_balance_eth),
          min_hold_time_minutes: parseOpt(wallet.min_hold_time_minutes),
          max_hold_time_minutes: parseOpt(wallet.max_hold_time_minutes),
          min_tokens_traded_7d: parseOpt(wallet.min_tokens_traded_7d),
          max_tokens_traded_7d: parseOpt(wallet.max_tokens_traded_7d),
          tokens_unique_period: wallet.tokens_unique_period,
        },
      }
      const res = await fetch('/api/hvat/filters', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`save ${res.status}`)
      setFlash('Фильтры сохранены')
      await refresh()
    } catch (e) {
      setFlash(e instanceof Error ? e.message : 'Ошибка сохранения')
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
          Токены по фильтрам → кошельки с одной сделкой → алерты на #2/#3 на низкой mcap.
        </p>
      </header>

      <div className="row gap actions">
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={() => void post('/api/hvat/enable', 'Хвать включён')}
        >
          Включить
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
        <button type="button" className="primary" disabled={busy} onClick={() => void saveFilters()}>
          Сохранить фильтры
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
        Период уникальных токенов: {wallet.tokens_unique_period} · порог 1-й сделки ≤{' '}
        {wallet.mcap_threshold || '—'}
        <br />
        Парс: {watch?.last_message || '—'} · след. {fmtTs(watch?.next_run_ts)}
        <br />
        Follow-up: {follow?.last_message || '—'} · след. {fmtTs(follow?.next_run_ts)}
      </p>
      {(watch?.last_error || follow?.last_error) && (
        <p className="error">{watch?.last_error || follow?.last_error}</p>
      )}

      <h2 className="section-title">Фильтры токенов</h2>
      <div className="filter-grid">
        <label className="field">
          <span>Мин. ликвидность ($)</span>
          <input type="number" min={0} value={screen.min_liq} onChange={(e) => setScreenField('min_liq', e.target.value)} placeholder="любая" />
        </label>
        <label className="field">
          <span>Макс. ликвидность ($)</span>
          <input type="number" min={0} value={screen.max_liq} onChange={(e) => setScreenField('max_liq', e.target.value)} placeholder="любая" />
        </label>
        <label className="field">
          <span>Мин. mcap ($)</span>
          <input type="number" min={0} value={screen.min_mcap} onChange={(e) => setScreenField('min_mcap', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Макс. mcap ($)</span>
          <input type="number" min={0} value={screen.max_mcap} onChange={(e) => setScreenField('max_mcap', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Мин. ATH mcap ($)</span>
          <input type="number" min={0} value={screen.min_ath_mcap} onChange={(e) => setScreenField('min_ath_mcap', e.target.value)} placeholder="выкл" />
        </label>
        <label className="field">
          <span>Мин. трейдеров (24ч)</span>
          <input type="number" min={0} value={screen.min_traders} onChange={(e) => setScreenField('min_traders', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Макс. трейдеров (24ч)</span>
          <input type="number" min={0} value={screen.max_traders} onChange={(e) => setScreenField('max_traders', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Мин. возраст пары (ч)</span>
          <input type="number" min={0} step={0.1} value={screen.min_pair_age_hours} onChange={(e) => setScreenField('min_pair_age_hours', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Макс. возраст пары (ч)</span>
          <input type="number" min={0} step={0.1} value={screen.max_pair_age_hours} onChange={(e) => setScreenField('max_pair_age_hours', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Сортировка</span>
          <select value={screen.sort_by} onChange={(e) => setScreenField('sort_by', e.target.value as ScreenSortBy)}>
            <option value="liquidity">Ликвидность</option>
            <option value="market_cap">Mcap</option>
            <option value="traders">Трейдеры</option>
            <option value="pair_age">Возраст пары</option>
          </select>
        </label>
        <label className="field">
          <span>Порядок</span>
          <select value={screen.sort_order} onChange={(e) => setScreenField('sort_order', e.target.value as ScreenSortOrder)}>
            <option value="desc">По убыванию</option>
            <option value="asc">По возрастанию</option>
          </select>
        </label>
        <label className="field">
          <span>Макс. результатов</span>
          <input type="number" min={1} max={2000} value={screen.max_results} onChange={(e) => setScreenField('max_results', e.target.value)} />
        </label>
        <label className="field">
          <span>Токенов за цикл</span>
          <input type="number" min={1} max={2000} value={maxTokensCycle} onChange={(e) => setMaxTokensCycle(e.target.value)} />
        </label>
        <label className="field checkbox-field">
          <span>Honeypot</span>
          <label className="check">
            <input
              type="checkbox"
              checked={screen.exclude_honeypots}
              onChange={(e) => setScreenField('exclude_honeypots', e.target.checked)}
            />
            Пропускать honeypot
          </label>
        </label>
      </div>

      <h2 className="section-title">Фильтры кошельков</h2>
      <div className="filter-grid">
        <label className="field">
          <span>Порог mcap 1-й сделки ($)</span>
          <input type="number" min={0} step={500} value={wallet.mcap_threshold} onChange={(e) => setWalletField('mcap_threshold', e.target.value)} />
        </label>
        <label className="field">
          <span>Мин. баланс (ETH)</span>
          <input type="number" min={0} step={0.001} value={wallet.min_wallet_balance_eth} onChange={(e) => setWalletField('min_wallet_balance_eth', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Макс. баланс (ETH)</span>
          <input type="number" min={0} step={0.001} value={wallet.max_wallet_balance_eth} onChange={(e) => setWalletField('max_wallet_balance_eth', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Мин. холд (мин)</span>
          <input type="number" min={0} value={wallet.min_hold_time_minutes} onChange={(e) => setWalletField('min_hold_time_minutes', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Макс. холд (мин)</span>
          <input type="number" min={0} value={wallet.max_hold_time_minutes} onChange={(e) => setWalletField('max_hold_time_minutes', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Мин. уникальных токенов</span>
          <input type="number" min={0} value={wallet.min_tokens_traded_7d} onChange={(e) => setWalletField('min_tokens_traded_7d', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Макс. уникальных токенов</span>
          <input type="number" min={0} value={wallet.max_tokens_traded_7d} onChange={(e) => setWalletField('max_tokens_traded_7d', e.target.value)} placeholder="любой" />
        </label>
        <label className="field">
          <span>Период уникальных токенов</span>
          <select
            value={wallet.tokens_unique_period}
            onChange={(e) =>
              setWalletField('tokens_unique_period', e.target.value as TokensUniquePeriod)
            }
          >
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="field checkbox-field">
          <span>Honeypot</span>
          <label className="check">
            <input
              type="checkbox"
              checked={wallet.exclude_honeypots}
              onChange={(e) => setWalletField('exclude_honeypots', e.target.checked)}
            />
            Пропускать honeypot токена
          </label>
        </label>
      </div>

      <h2 className="section-title">Кошельки в слежке</h2>
      {wallets.length === 0 ? (
        <p className="empty">Пока пусто — сохрани фильтры, включи Хвать и дождись автопарса.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Кошелёк</th>
                <th>Сделок</th>
                <th>1-я mcap</th>
                <th>Уник. токены</th>
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
