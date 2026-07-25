import { useCallback, useEffect, useMemo, useState } from 'react'

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

export default function ScreenerPage({ onUseInBuyers }: Props) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [job, setJob] = useState<ScreenJobResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<TableSortKey>('liquidity_usd')
  const [sortAsc, setSortAsc] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(() => new Set())

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters((f) => ({ ...f, [key]: value }))
  }

  useEffect(() => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return
    const id = job.job_id
    const t = setInterval(async () => {
      try {
        const res = await fetch(`/api/screen/${id}`)
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
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(addr)) next.delete(addr)
      else next.add(addr)
      return next
    })
  }

  const toggleAllVisible = () => {
    setSelected((prev) => {
      const next = new Set(prev)
      const allSelected = filtered.every((r) => next.has(r.address))
      if (allSelected) {
        for (const r of filtered) next.delete(r.address)
      } else {
        for (const r of filtered) next.add(r.address)
      }
      return next
    })
  }

  const progress = job?.progress.percent ?? 0
  const sortDir = sortAsc ? '↑' : '↓'

  return (
    <>
      <header className="hero">
        <p className="brand">gnomode</p>
        <h1>Token screener</h1>
        <p className="lede">
          Scan Robinhood Chain tokens with liquidity, age, traders, and market-cap filters.
        </p>
      </header>

      <section className="panel input-panel">
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
              {selected.size > 0 && onUseInBuyers && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => onUseInBuyers([...selected])}
                >
                  Use in Early buyers ({selected.size})
                </button>
              )}
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
                      checked={filtered.length > 0 && filtered.every((r) => selected.has(r.address))}
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
                {filtered.map((r) => (
                  <tr key={r.address}>
                    <td className="check-col">
                      <input
                        type="checkbox"
                        checked={selected.has(r.address)}
                        onChange={() => toggleSelect(r.address)}
                        aria-label={`Select ${r.symbol || r.address}`}
                      />
                    </td>
                    <td>
                      <a href={r.gmgn_url || `https://gmgn.ai/robinhood/token/${r.address}`} target="_blank" rel="noreferrer" title={r.address}>
                        <strong>{r.symbol || shortAddr(r.address)}</strong>
                      </a>
                      <div className="mono muted">{shortAddr(r.address)}</div>
                    </td>
                    <td>${fmtNum(r.price_usd, 6)}</td>
                    <td>${fmtNum(r.liquidity_usd, 0)}</td>
                    <td>${fmtNum(r.market_cap, 0)}</td>
                    <td>{fmtNum(r.traders_24h, 0)}</td>
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
                ))}
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
