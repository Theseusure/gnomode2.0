/** localStorage helpers for restoring UI sessions across reloads. */

export function loadJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function saveJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // quota / private mode — ignore
  }
}

export function clearJson(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore
  }
}
