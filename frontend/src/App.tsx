import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'

type BuyerRow = {
  wallet: string
  token: string
  token_symbol: string
  bought_tokens: number
  bought_usd: number
  mcap_at_first_buy: number
  buys_count: number
  first_tx: string
  first_block: number
}

type TokenResult = {
  token: string
  symbol: string
  name: string
  decimals: number
  total_supply: number
  pool: {
    address: string
    dex: string
    quote_symbol: string
    liquidity_usd: number
  } | null
  buyers: BuyerRow[]
  error: string | null
  stats: Record<string, unknown>
}

type JobProgress = {
  stage: string
  message: string
  percent: number
  current_token: string | null
}

type JobResponse = {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'error'
  progress: JobProgress
  results: TokenResult[]
  error: string | null
}

type SortKey = 'mcap_at_first_buy' | 'bought_usd' | 'bought_tokens' | 'buys_count' | 'wallet'

function shortAddr(a: string) {
  if (!a || a.length < 12) return a
  return `${a.slice(0, 6)}…${a.slice(-4)}`
}

function gmgnToken(addr: string) {
  return `https://gmgn.ai/robinhood/token/${addr}`
}

function gmgnWallet(addr: string) {
  return `https://gmgn.ai/robinhood/address/${addr}`
}

function fmtNum(n: number, digits = 2) {
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function exportCsv(rows: BuyerRow[]) {
  const header = [
    'wallet',
    'token',
    'symbol',
    'bought_tokens',
    'bought_usd',
    'mcap_at_first_buy',
    'buys_count',
    'first_tx',
    'first_block',
  ]
  const lines = [header.join(',')]
  for (const r of rows) {
    lines.push(
      [
        r.wallet,
        r.token,
        r.token_symbol,
        r.bought_tokens,
        r.bought_usd,
        r.mcap_at_first_buy,
        r.buys_count,
        r.first_tx,
        r.first_block,
      ].join(','),
    )
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `early-buyers-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function App() {
  const [input, setInput] = useState('')
  const [threshold, setThreshold] = useState(15000)
  const [job, setJob] = useState<JobResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('mcap_at_first_buy')
  const [sortAsc, setSortAsc] = useState(true)
  const [busy, setBusy] = useState(false)

  const allBuyers = useMemo(() => {
    if (!job?.results) return []
    return job.results.flatMap((r) =>
      r.buyers.map((b) => ({ ...b, token_symbol: b.token_symbol || r.symbol })),
    )
  }, [job])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let rows = allBuyers
    if (q) {
      rows = rows.filter(
        (r) =>
          r.wallet.toLowerCase().includes(q) ||
          r.token.toLowerCase().includes(q) ||
          r.token_symbol.toLowerCase().includes(q),
      )
    }
    const mul = sortAsc ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'string' && typeof bv === 'string') {
        return av.localeCompare(bv) * mul
      }
      return ((av as number) - (bv as number)) * mul
    })
  }, [allBuyers, query, sortKey, sortAsc])

  useEffect(() => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return
    const id = job.job_id
    const t = setInterval(async () => {
      try {
        const res = await fetch(`/api/parse/${id}`)
        if (!res.ok) throw new Error(await res.text())
        const data = (await res.json()) as JobResponse
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

  const startParse = useCallback(async () => {
    setError(null)
    setJob(null)
    const tokens = input
      .split(/[\s,;]+/)
      .map((t) => t.trim())
      .filter(Boolean)
    if (!tokens.length) {
      setError('Paste at least one token address')
      return
    }
    setBusy(true)
    try {
      const res = await fetch('/api/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tokens, mcap_threshold: threshold }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = (await res.json()) as JobResponse
      setJob(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }, [input, threshold])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v)
    else {
      setSortKey(key)
      setSortAsc(key === 'mcap_at_first_buy')
    }
  }

  const progress = job?.progress.percent ?? 0

  const sortDir = sortAsc ? '↑' : '↓'

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">gnomode</p>
        <h1>Early buyers on Robinhood Chain</h1>
        <p className="lede">
          Find wallets that bought a token while market cap was still under your threshold.
        </p>
      </header>

      <section className="panel input-panel">
        <label className="field">
          <span>Token address(es)</span>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="0x… one per line, or comma-separated"
            rows={4}
            spellCheck={false}
          />
        </label>
        <div className="row">
          <label className="field compact">
            <span>Mcap threshold (USD)</span>
            <input
              type="number"
              min={0}
              step={500}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value) || 0)}
            />
          </label>
          <button
            className={`primary${busy ? ' busy' : ''}`}
            disabled={busy}
            onClick={startParse}
          >
            {busy ? 'Parsing…' : 'Parse'}
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

      {job?.results?.some((r) => r.error || r.pool) && (
        <section className="panel meta-panel">
          {job.results.map((r) => (
            <div key={r.token} className="token-meta">
              <div>
                <a
                  href={gmgnToken(r.token)}
                  target="_blank"
                  rel="noreferrer"
                  title={r.token}
                >
                  <strong>{r.symbol || shortAddr(r.token)}</strong>
                </a>
                {!r.error && (
                  <span className="badge">{r.buyers.length} wallets</span>
                )}
                <a
                  className="mono muted"
                  href={gmgnToken(r.token)}
                  target="_blank"
                  rel="noreferrer"
                  title={r.token}
                >
                  {' '}
                  {shortAddr(r.token)}
                </a>
              </div>
              {r.error ? (
                <p className="err">{r.error}</p>
              ) : (
                <p className="muted">
                  {r.pool?.dex} · {r.pool?.quote_symbol}
                  {r.pool && (
                    <>
                      {' · '}
                      <a
                        href={`https://robinhoodchain.blockscout.com/address/${r.pool.address}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        pool
                      </a>
                    </>
                  )}
                </p>
              )}
            </div>
          ))}
        </section>
      )}

      {allBuyers.length > 0 && (
        <section className="panel table-panel">
          <div className="table-toolbar">
            <input
              className="search"
              placeholder="Filter by wallet / token…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              spellCheck={false}
            />
            <div className="toolbar-right">
              <span className="muted">{filtered.length} wallets</span>
              <button type="button" className="ghost" onClick={() => exportCsv(filtered)}>
                Export CSV
              </button>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th
                    className={sortKey === 'wallet' ? 'active' : undefined}
                    data-dir={sortKey === 'wallet' ? sortDir : undefined}
                    onClick={() => toggleSort('wallet')}
                  >
                    Wallet
                  </th>
                  <th>Token</th>
                  <th
                    className={sortKey === 'bought_tokens' ? 'active' : undefined}
                    data-dir={sortKey === 'bought_tokens' ? sortDir : undefined}
                    onClick={() => toggleSort('bought_tokens')}
                  >
                    Bought
                  </th>
                  <th
                    className={sortKey === 'bought_usd' ? 'active' : undefined}
                    data-dir={sortKey === 'bought_usd' ? sortDir : undefined}
                    onClick={() => toggleSort('bought_usd')}
                  >
                    USD ≈
                  </th>
                  <th
                    className={sortKey === 'mcap_at_first_buy' ? 'active' : undefined}
                    data-dir={sortKey === 'mcap_at_first_buy' ? sortDir : undefined}
                    onClick={() => toggleSort('mcap_at_first_buy')}
                  >
                    Mcap at buy
                  </th>
                  <th
                    className={sortKey === 'buys_count' ? 'active' : undefined}
                    data-dir={sortKey === 'buys_count' ? sortDir : undefined}
                    onClick={() => toggleSort('buys_count')}
                  >
                    Buys
                  </th>
                  <th>Tx</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={`${r.token}-${r.wallet}-${r.first_tx}`}>
                    <td className="mono">
                      <a
                        href={gmgnWallet(r.wallet)}
                        target="_blank"
                        rel="noreferrer"
                        title={r.wallet}
                      >
                        {shortAddr(r.wallet)}
                      </a>
                    </td>
                    <td>
                      <a
                        href={gmgnToken(r.token)}
                        target="_blank"
                        rel="noreferrer"
                        title={r.token}
                      >
                        {r.token_symbol || shortAddr(r.token)}
                      </a>
                    </td>
                    <td>{fmtNum(r.bought_tokens, 4)}</td>
                    <td>${fmtNum(r.bought_usd, 2)}</td>
                    <td>${fmtNum(r.mcap_at_first_buy, 0)}</td>
                    <td>{r.buys_count}</td>
                    <td className="mono">
                      {r.first_tx ? (
                        <a
                          href={`https://robinhoodchain.blockscout.com/tx/${r.first_tx}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {shortAddr(r.first_tx)}
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {job?.status === 'done' && allBuyers.length === 0 && !job.results.some((r) => r.error) && (
        <p className="empty">No early buyers found under ${fmtNum(threshold, 0)} mcap.</p>
      )}

      <footer className="foot">
        Robinhood Chain · Uniswap V2/V3/V4 · public RPC by default
      </footer>
    </div>
  )
}
