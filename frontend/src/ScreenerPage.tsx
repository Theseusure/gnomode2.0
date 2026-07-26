import { useCallback, useEffect, useMemo, useState } from 'react'
import { FilterPresets } from './FilterPresets'
import { loadJson, saveJson } from './session'

const SCREEN_SESSION_KEY = 'gnomode.session.screener'

type ScreenedToken = {
  address: string
  symbol: string
  name: string
  pair_address: string
  dex_id: string
  price_usd: number
  liquidity_usd: number
  market_cap: number
  traders_24h: number
  buys_24h?: number
  sells_24h?: number
  pair_created_at_ms: number | null
  pair_age_hours: number | null
  url: string
  gmgn_url: string
}

type JobProgress = {
  stage: string
  message: string
  percent: number
  current_token: string | null
}

type ScreenJobResponse = {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'error'
  progress: JobProgress
  results: ScreenedToken[]
  error: string | null
}

type IndexStatus = {
  tokens_24h: number
  enriched: number
  building: boolean
  cold_started: boolean
  refreshing: boolean
  last_tip: number
  last_scan_ts: number
  last_refresh_ts: number
  window_hours: number
}

type ScreenSortBy = 'liquidity' | 'market_cap' | 'traders' | 'pair_age'
type ScreenSortOrder = 'asc' | 'desc'
type TableSortKey =
  | 'symbol'
  | 'liquidity_usd'
  | 'market_cap'
  | 'traders_24h'
  | 'pair_age_hours'
  | 'price_usd'

type Filters = {
  min_liq: string
  max_liq: string
  min_mcap: string
  max_mcap: string
  min_traders: string
  max_traders: string
  min_pair_age_hours: string
  max_pair_age_hours: string
  sort_by: ScreenSortBy
  sort_order: ScreenSortOrder
  max_results: string
  exclude_honeypots: boolean
}

const DEFAULT_FILTERS: Filters = {
  min_liq: '',
  max_liq: '',
  min_mcap: '',
  max_mcap: '',
  min_traders: '',
  max_traders: '',
  min_pair_age_hours: '',
  max_pair_age_hours: '',
  sort_by: 'liquidity',
  sort_order: 'desc',
  max_results: '500',
  exclude_honeypots: true,
}

function shortAddr(a: string) {
  if (!a || a.length < 12) return a
  return `${a.slice(0, 6)}…${a.slice(-4)}`
}

function fmtNum(n: number, digits = 2) {
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function fmtAge(hours: number | null) {
  if (hours == null || !Number.isFinite(hours)) return '—'
  if (hours < 24) return `${fmtNum(hours, 1)}h`
  return `${fmtNum(hours / 24, 1)}d`
}

function fmtAgo(tsSeconds: number) {
  if (!tsSeconds) return 'never'
  const secs = Math.max(0, Date.now() / 1000 - tsSeconds)
  if (secs < 60) return `${Math.round(secs)}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  return `${Math.round(secs / 3600)}h ago`
}

function parseOpt(raw: string): number | null {
  const t = raw.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function exportCsv(rows: ScreenedToken[]) {
  const header = [
    'address',
    'symbol',
    'name',
    'pair_address',
    'dex_id',
    'price_usd',
    'liquidity_usd',
    'market_cap',
    'traders_24h',
    'pair_age_hours',
    'url',
    'gmgn_url',
  ]
  const lines = [header.join(',')]
  for (const r of rows) {
    lines.push(
      [
        r.address,
        r.symbol,
        JSON.stringify(r.name),
        r.pair_address,
        r.dex_id,
        r.price_usd,
        r.liquidity_usd,
        r.market_cap,
        r.traders_24h,
        r.pair_age_hours ?? '',
        r.url,
        r.gmgn_url,
      ].join(','),
    )
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `screened-tokens-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

type Props = {
  onUseInBuyers?: (addresses: string[]) => void
}

type ScreenSession = {
  v: 1
  filters: Filters
  query: string
  sortKey: TableSortKey
  sortAsc: boolean
  selected: string[]
  job: ScreenJobResponse | null
}

function loadScreenSession(): ScreenSession | null {
  const raw = loadJson<ScreenSession>(SCREEN_SESSION_KEY)
  if (!raw || raw.v !== 1) return null
  return raw
}

export default function ScreenerPage({ onUseInBuyers }: Props) {
  const restored = useMemo(() => loadScreenSession(), [])
  const [filters, setFilters] = useState<Filters>(
    restored?.filters ? { ...DEFAULT_FILTERS, ...restored.filters } : DEFAULT_FILTERS,
  )
  const [job, setJob] = useState<ScreenJobResponse | null>(restored?.job ?? null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(
    () => restored?.job?.status === 'queued' || restored?.job?.status === 'running',
  )
  const [query, setQuery] = useState(restored?.query ?? '')
  const [sortKey, setSortKey] = useState<TableSortKey>(
    restored?.sortKey ?? 'liquidity_usd',
  )
  const [sortAsc, setSortAsc] = useState(restored?.sortAsc ?? false)
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(restored?.selected ?? []),
  )
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null)

  useEffect(() => {
    saveJson(SCREEN_SESSION_KEY, {
      v: 1,
      filters,
      query,
      sortKey,
      sortAsc,
      selected: [...selected],
      job,
    } satisfies ScreenSession)
  }, [filters, query, sortKey, sortAsc, selected, job])

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters((f) => ({ ...f, [key]: value }))
  }

  const applyPreset = useCallback((values: Filters) => {
    setFilters({ ...DEFAULT_FILTERS, ...values })
  }, [])

  const keyOf = (addr: string) => addr.toLowerCase()

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const res = await fetch('/api/index/status')
        if (!res.ok) return
        const data = (await res.json()) as IndexStatus
        if (alive) setIndexStatus(data)
      } catch {
        /* ignore transient status errors */
      }
    }
    poll()
    const t = setInterval(poll, 5000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  const refreshIndex = useCallback(async () => {
    try {
      const res = await fetch('/api/index/refresh', { method: 'POST' })
      if (res.ok) setIndexStatus((await res.json()) as IndexStatus)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return
    const id = job.job_id
    const t = setInterval(async () => {
      try {
        const res = await fetch(`/api/screen/${id}`)
        if (res.status === 404) {
          setJob((prev) =>
            prev
              ? {
                  ...prev,
                  status: 'error',
                  error:
                    'Job lost after server restart. Showing last saved snapshot.',
                  progress: {
                    ...prev.progress,
                    stage: 'error',
                    message: 'Job lost — restored from session',
                  },
                }
              : prev,
          )
          setBusy(false)
          return
        }
        if (!res.ok) throw new Error(await res.text())
        const data = (await res.json()) as ScreenJobResponse
        setJob(data)
        if (data.status === 'done' || data.status === 'error') {
          setBusy(false)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        setBusy(false)
      }
    }, 1200)
    return () => clearInterval(t)
  }, [job?.job_id, job?.status])

  const startScreen = useCallback(async () => {
    setError(null)
    setJob(null)
    setSelected(new Set())
    setBusy(true)
    const maxResults = parseOpt(filters.max_results)
    try {
      const res = await fetch('/api/screen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          min_liq: parseOpt(filters.min_liq),
          max_liq: parseOpt(filters.max_liq),
          min_mcap: parseOpt(filters.min_mcap),
          max_mcap: parseOpt(filters.max_mcap),
          min_traders: parseOpt(filters.min_traders),
          max_traders: parseOpt(filters.max_traders),
          min_pair_age_hours: parseOpt(filters.min_pair_age_hours),
          max_pair_age_hours: parseOpt(filters.max_pair_age_hours),
          sort_by: filters.sort_by,
          sort_order: filters.sort_order,
          max_results: maxResults ?? 500,
          exclude_honeypots: filters.exclude_honeypots,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = (await res.json()) as ScreenJobResponse
      setJob(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }, [filters])

  const rows = job?.results ?? []

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let list = rows
    if (q) {
      list = list.filter(
        (r) =>
          r.address.toLowerCase().includes(q) ||
          r.symbol.toLowerCase().includes(q) ||
          r.name.toLowerCase().includes(q),
      )
    }
    const mul = sortAsc ? 1 : -1
    return [...list].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'string' && typeof bv === 'string') {
        return av.localeCompare(bv) * mul
      }
      const an = av == null ? -Infinity : (av as number)
      const bn = bv == null ? -Infinity : (bv as number)
      return (an - bn) * mul
    })
  }, [rows, query, sortKey, sortAsc])

  const toggleSort = (key: TableSortKey) => {
    if (sortKey === key) setSortAsc((v) => !v)
    else {
      setSortKey(key)
      setSortAsc(key === 'symbol')
    }
  }

  const toggleSelect = (addr: string) => {
    const key = keyOf(addr)
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleAllVisible = () => {
    setSelected((prev) => {
      const next = new Set(prev)
      const allSelected = filtered.every((r) => next.has(keyOf(r.address)))
      if (allSelected) {
        for (const r of filtered) next.delete(keyOf(r.address))
      } else {
        for (const r of filtered) next.add(keyOf(r.address))
      }
      return next
    })
  }

  const clearSelection = () => setSelected(new Set())

  const selectedOrdered = useMemo(() => {
    const keys = selected
    const fromRows = rows.filter((r) => keys.has(keyOf(r.address))).map((r) => r.address)
    // preserve table order for visible first, then any leftover
    const seen = new Set(fromRows.map(keyOf))
    const extras = [...keys].filter((k) => !seen.has(k))
    return [...fromRows, ...extras]
  }, [rows, selected])

  const sendToBuyers = () => {
    if (!onUseInBuyers || selectedOrdered.length === 0) return
    onUseInBuyers(selectedOrdered)
  }

  const allVisibleSelected =
    filtered.length > 0 && filtered.every((r) => selected.has(keyOf(r.address)))

  const progress = job?.progress.percent ?? 0
  const sortDir = sortAsc ? '↑' : '↓'

  return (
    <>
      <header className="hero">
        <p className="brand">gnomode</p>
        <h1>Token screener</h1>
        <p className="lede">
          All new Robinhood Chain tokens from the last 24h (Uniswap V3/V4), with liquidity,
          age, traders, and market-cap filters.
        </p>
      </header>

      <section className="index-status">
        <div className="index-status-meta">
          {indexStatus ? (
            indexStatus.building && !indexStatus.cold_started ? (
              <span className="idx-build">Building 24h index… {fmtNum(indexStatus.enriched, 0)} tokens ready</span>
            ) : (
              <span>
                <strong>{fmtNum(indexStatus.tokens_24h, 0)}</strong> new tokens (24h)
                <span className="muted">
                  {' '}· {fmtNum(indexStatus.enriched, 0)} enriched · updated{' '}
                  {fmtAgo(indexStatus.last_refresh_ts)}
                  {indexStatus.refreshing ? ' · refreshing…' : ''}
                </span>
              </span>
            )
          ) : (
            <span className="muted">Loading index status…</span>
          )}
        </div>
        <button
          type="button"
          className="ghost compact-btn"
          onClick={refreshIndex}
          disabled={!!indexStatus?.refreshing}
        >
          {indexStatus?.refreshing ? 'Refreshing…' : 'Refresh index'}
        </button>
      </section>

      <section className="panel input-panel">
        <FilterPresets
          storageKey="gnomode.presets.tokens"
          current={filters}
          onApply={applyPreset}
          disabled={busy}
        />
        <div className="filter-grid">
          <label className="field">
            <span>Min liquidity ($)</span>
            <input
              type="number"
              min={0}
              value={filters.min_liq}
              onChange={(e) => setFilter('min_liq', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Max liquidity ($)</span>
            <input
              type="number"
              min={0}
              value={filters.max_liq}
              onChange={(e) => setFilter('max_liq', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Min mcap ($)</span>
            <input
              type="number"
              min={0}
              value={filters.min_mcap}
              onChange={(e) => setFilter('min_mcap', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Max mcap ($)</span>
            <input
              type="number"
              min={0}
              value={filters.max_mcap}
              onChange={(e) => setFilter('max_mcap', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Min traders (24h txns)</span>
            <input
              type="number"
              min={0}
              value={filters.min_traders}
              onChange={(e) => setFilter('min_traders', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Max traders (24h txns)</span>
            <input
              type="number"
              min={0}
              value={filters.max_traders}
              onChange={(e) => setFilter('max_traders', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Min pair age (hours)</span>
            <input
              type="number"
              min={0}
              value={filters.min_pair_age_hours}
              onChange={(e) => setFilter('min_pair_age_hours', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Max pair age (hours)</span>
            <input
              type="number"
              min={0}
              value={filters.max_pair_age_hours}
              onChange={(e) => setFilter('max_pair_age_hours', e.target.value)}
              placeholder="any"
            />
          </label>
          <label className="field">
            <span>Sort by</span>
            <select
              value={filters.sort_by}
              onChange={(e) => setFilter('sort_by', e.target.value as ScreenSortBy)}
            >
              <option value="liquidity">Liquidity</option>
              <option value="market_cap">Market cap</option>
              <option value="traders">Traders</option>
              <option value="pair_age">Pair age</option>
            </select>
          </label>
          <label className="field">
            <span>Order</span>
            <select
              value={filters.sort_order}
              onChange={(e) => setFilter('sort_order', e.target.value as ScreenSortOrder)}
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
          <label className="field">
            <span>Max results</span>
            <input
              type="number"
              min={1}
              max={2000}
              value={filters.max_results}
              onChange={(e) => setFilter('max_results', e.target.value)}
            />
          </label>
          <label className="field check-field">
            <span>Security</span>
            <label className="check-inline">
              <input
                type="checkbox"
                checked={filters.exclude_honeypots}
                onChange={(e) => setFilter('exclude_honeypots', e.target.checked)}
              />
              Skip honeypots (GMGN)
            </label>
          </label>
        </div>

        <div className="row">
          <button
            className={`primary${busy ? ' busy' : ''}`}
            disabled={busy}
            onClick={startScreen}
          >
            {busy ? 'Screening…' : 'Screen tokens'}
          </button>
          <button
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() => setFilters(DEFAULT_FILTERS)}
          >
            Reset filters
          </button>
        </div>

        {error && <p className="err">{error}</p>}
        {job && (job.status === 'queued' || job.status === 'running') && (
          <div className="progress-wrap">
            <div className="progress-meta">
              <span>{job.progress.message || job.progress.stage}</span>
              <span className="pct">{fmtNum(progress, 1)}%</span>
            </div>
            <div className="bar">
              <div className="bar-fill" style={{ width: `${Math.min(progress, 100)}%` }} />
            </div>
          </div>
        )}
        {job?.status === 'error' && <p className="err">{job.error || 'Job failed'}</p>}
      </section>

      {rows.length > 0 && (
        <section className="panel table-panel">
          <div className="selection-bar">
            <div className="selection-meta">
              <span>
                Выбрано: <strong>{selected.size}</strong>
                <span className="muted"> / {filtered.length} в таблице</span>
              </span>
              <button type="button" className="ghost compact-btn" onClick={toggleAllVisible}>
                {allVisibleSelected ? 'Снять все' : 'Выбрать все'}
              </button>
              {selected.size > 0 && (
                <button type="button" className="ghost compact-btn" onClick={clearSelection}>
                  Очистить
                </button>
              )}
            </div>
            <button
              type="button"
              className="primary"
              disabled={!onUseInBuyers || selected.size === 0}
              onClick={sendToBuyers}
            >
              {selected.size > 0
                ? `В парсинг кошельков (${selected.size})`
                : 'В парсинг кошельков'}
            </button>
          </div>

          <div className="table-toolbar">
            <input
              className="search"
              placeholder="Filter by symbol / address…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              spellCheck={false}
            />
            <div className="toolbar-right">
              <span className="muted">{filtered.length} tokens</span>
              <button type="button" className="ghost" onClick={() => exportCsv(filtered)}>
                Export CSV
              </button>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th className="check-col">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleAllVisible}
                      aria-label="Select all"
                    />
                  </th>
                  <th
                    className={sortKey === 'symbol' ? 'active' : undefined}
                    data-dir={sortKey === 'symbol' ? sortDir : undefined}
                    onClick={() => toggleSort('symbol')}
                  >
                    Token
                  </th>
                  <th
                    className={sortKey === 'price_usd' ? 'active' : undefined}
                    data-dir={sortKey === 'price_usd' ? sortDir : undefined}
                    onClick={() => toggleSort('price_usd')}
                  >
                    Price
                  </th>
                  <th
                    className={sortKey === 'liquidity_usd' ? 'active' : undefined}
                    data-dir={sortKey === 'liquidity_usd' ? sortDir : undefined}
                    onClick={() => toggleSort('liquidity_usd')}
                  >
                    Liquidity
                  </th>
                  <th
                    className={sortKey === 'market_cap' ? 'active' : undefined}
                    data-dir={sortKey === 'market_cap' ? sortDir : undefined}
                    onClick={() => toggleSort('market_cap')}
                  >
                    Mcap
                  </th>
                    <th
                    className={sortKey === 'traders_24h' ? 'active' : undefined}
                    data-dir={sortKey === 'traders_24h' ? sortDir : undefined}
                    onClick={() => toggleSort('traders_24h')}
                  >
                    Traders
                  </th>
                  <th>B/S</th>
                  <th
                    className={sortKey === 'pair_age_hours' ? 'active' : undefined}
                    data-dir={sortKey === 'pair_age_hours' ? sortDir : undefined}
                    onClick={() => toggleSort('pair_age_hours')}
                  >
                    Age
                  </th>
                  <th>Links</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => {
                  const isSelected = selected.has(keyOf(r.address))
                  return (
                    <tr
                      key={r.address}
                      className={isSelected ? 'row-selected' : undefined}
                      onClick={(e) => {
                        const target = e.target as HTMLElement
                        if (target.closest('a, input, button')) return
                        toggleSelect(r.address)
                      }}
                    >
                      <td className="check-col">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(r.address)}
                          aria-label={`Select ${r.symbol || r.address}`}
                        />
                      </td>
                      <td>
                        <a
                          href={r.gmgn_url || `https://gmgn.ai/robinhood/token/${r.address}`}
                          target="_blank"
                          rel="noreferrer"
                          title={r.address}
                        >
                          <strong>{r.symbol || shortAddr(r.address)}</strong>
                        </a>
                        <div className="mono muted">{shortAddr(r.address)}</div>
                      </td>
                      <td>${fmtNum(r.price_usd, 6)}</td>
                      <td>${fmtNum(r.liquidity_usd, 0)}</td>
                      <td>${fmtNum(r.market_cap, 0)}</td>
                      <td>{fmtNum(r.traders_24h, 0)}</td>
                      <td className="mono muted">
                        {fmtNum(r.buys_24h ?? 0, 0)}/{fmtNum(r.sells_24h ?? 0, 0)}
                      </td>
                      <td>{fmtAge(r.pair_age_hours)}</td>
                      <td className="mono">
                        {r.url && (
                          <a href={r.url} target="_blank" rel="noreferrer">
                            dex
                          </a>
                        )}
                        {r.url && r.gmgn_url ? ' · ' : null}
                        {r.gmgn_url && (
                          <a href={r.gmgn_url} target="_blank" rel="noreferrer">
                            gmgn
                          </a>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {job?.status === 'done' && rows.length === 0 && (
        <p className="empty">No tokens matched these filters.</p>
      )}
    </>
  )
}
