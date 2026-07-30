import { useMemo, useState } from 'react'

type Token = {
  launchpad: string; address: string; name?: string | null; symbol?: string | null
  migrated_at?: string | null; source_url: string; verification: string
  liquidity_usd: number; traders_24h: number
}
type Response = { tokens: Token[]; errors: Record<string, string>; count: number; duration_ms: number }
const short = (address: string) => `${address.slice(0, 8)}…${address.slice(-6)}`

export default function MigrationsPage({ onParse }: { onParse: (addresses: string[]) => void }) {
  const [pons, setPons] = useState(true)
  const [flap, setFlap] = useState(true)
  const [age, setAge] = useState('1')
  const [minLiquidity, setMinLiquidity] = useState('')
  const [minTraders, setMinTraders] = useState('')
  const [query, setQuery] = useState('')
  const [data, setData] = useState<Response | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? (data?.tokens ?? []).filter((t) =>
      [t.address, t.name, t.symbol, t.launchpad].some((v) => v?.toLowerCase().includes(q)),
    ) : data?.tokens ?? []
  }, [data, query])

  async function scan() {
    const launchpads = [pons && 'pons', flap && 'flap'].filter(Boolean).join(',')
    if (!launchpads) return
    setBusy(true); setError(null)
    try {
      const p = new URLSearchParams({ launchpads })
      if (age) p.set('max_age_hours', age)
      if (minLiquidity) p.set('min_liquidity_usd', minLiquidity)
      if (minTraders) p.set('min_traders_24h', minTraders)
      const r = await fetch(`/api/migrations?${p}`)
      if (!r.ok) throw new Error(await r.text())
      setData(await r.json() as Response); setSelected(new Set())
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  function toggle(address: string) {
    setSelected((old) => { const next = new Set(old); const key = address.toLowerCase()
      if (next.has(key)) next.delete(key); else next.add(key); return next })
  }
  return <>
    <header className="hero">
      <p className="brand">launch radar × gnomode</p>
      <h1>Миграции Pons и Flap</h1>
      <p className="lede">Только graduation Pons и on-chain LaunchedToDEX Flap.</p>
    </header>
    <section className="panel input-panel">
      <div className="row">
        <label className="check-inline"><input type="checkbox" checked={pons} onChange={(e) => setPons(e.target.checked)} />Pons migrated</label>
        <label className="check-inline"><input type="checkbox" checked={flap} onChange={(e) => setFlap(e.target.checked)} />Flap migrated</label>
        <label className="field compact"><span>Возраст, ч</span><input type="number" min={0} value={age} onChange={(e) => setAge(e.target.value)} /></label>
        <label className="field compact"><span>Мин. ликвидность, $</span><input type="number" min={0} value={minLiquidity} onChange={(e) => setMinLiquidity(e.target.value)} /></label>
        <label className="field compact"><span>Мин. трейдеров 24ч</span><input type="number" min={0} value={minTraders} onChange={(e) => setMinTraders(e.target.value)} /></label>
        <button className={`primary${busy ? ' busy' : ''}`} disabled={busy} onClick={scan}>{busy ? 'Сканирование…' : 'Найти миграции'}</button>
      </div>
      {error && <p className="err">{error}</p>}
      {data && <p className="muted">{data.count} миграций · {(data.duration_ms / 1000).toFixed(1)} с
        {Object.keys(data.errors).length ? ` · ошибки: ${Object.keys(data.errors).join(', ')}` : ''}</p>}
    </section>
    {data && <section className="panel table-panel">
      <div className="table-tools">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Имя, тикер или адрес" />
        <button className="primary" disabled={!selected.size} onClick={() => onParse([...selected])}>В Early buyers ({selected.size})</button>
      </div>
      <div className="table-scroll"><table><thead><tr><th /><th>Токен</th><th>Launchpad</th><th>Миграция</th><th>Ликвидность</th><th>Трейдеры</th><th>Проверка</th></tr></thead>
        <tbody>{visible.map((t) => <tr key={`${t.launchpad}:${t.address}`}>
          <td><input type="checkbox" checked={selected.has(t.address.toLowerCase())} onChange={() => toggle(t.address)} /></td>
          <td><a href={`https://gmgn.ai/robinhood/token/${t.address}`} target="_blank" rel="noreferrer"><strong>{t.symbol || t.name || short(t.address)}</strong></a><div className="mono muted">{short(t.address)}</div></td>
          <td><span className="badge">{t.launchpad.toUpperCase()}</span></td>
          <td>{t.migrated_at ? new Date(t.migrated_at).toLocaleString() : 'confirmed'}</td>
          <td>${t.liquidity_usd.toLocaleString()}</td><td>{t.traders_24h.toLocaleString()}</td>
          <td><a href={t.source_url} target="_blank" rel="noreferrer">{t.verification} ↗</a></td>
        </tr>)}</tbody></table></div>
    </section>}
  </>
}
