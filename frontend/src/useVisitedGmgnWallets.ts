import { useCallback, useState } from 'react'

const STORAGE_KEY = 'gnomode.visitedGmgnWallets'

function loadVisited(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return new Set()
    return new Set(
      parsed
        .filter((a): a is string => typeof a === 'string' && a.startsWith('0x'))
        .map((a) => a.toLowerCase()),
    )
  } catch {
    return new Set()
  }
}

function persist(next: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]))
  } catch {
    // quota / private mode — ignore
  }
}

/** Wallets opened on GMGN — persisted across browser sessions. */
export function useVisitedGmgnWallets() {
  const [visited, setVisited] = useState<Set<string>>(() => loadVisited())

  const markVisited = useCallback((addr: string) => {
    const key = addr.toLowerCase()
    setVisited((prev) => {
      if (prev.has(key)) return prev
      const next = new Set(prev)
      next.add(key)
      persist(next)
      return next
    })
  }, [])

  const clearVisited = useCallback(() => {
    setVisited(new Set())
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignore
    }
  }, [])

  const isVisited = useCallback(
    (addr: string) => visited.has(addr.toLowerCase()),
    [visited],
  )

  return { visited, markVisited, clearVisited, isVisited, visitedCount: visited.size }
}
