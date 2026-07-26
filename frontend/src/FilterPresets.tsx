import { useCallback, useState } from 'react'

type StoredPreset<T> = {
  name: string
  values: T
  saved_at: number
}

function loadPresets<T>(storageKey: string): StoredPreset<T>[] {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (p): p is StoredPreset<T> =>
        !!p &&
        typeof p === 'object' &&
        typeof (p as StoredPreset<T>).name === 'string' &&
        typeof (p as StoredPreset<T>).values === 'object',
    )
  } catch {
    return []
  }
}

function persistPresets<T>(storageKey: string, presets: StoredPreset<T>[]) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(presets))
  } catch {
    // quota / private mode — ignore
  }
}

type Props<T> = {
  /** localStorage key, e.g. "gnomode.presets.wallets" */
  storageKey: string
  /** Current filter values (saved when the user hits "Сохранить"). */
  current: T
  /** Called with the stored values when the user picks a preset. */
  onApply: (values: T) => void
  disabled?: boolean
}

/**
 * Save/load named filter presets, persisted in localStorage.
 * Generic over the filter shape so the same bar works for wallet and token filters.
 */
export function FilterPresets<T extends object>({
  storageKey,
  current,
  onApply,
  disabled,
}: Props<T>) {
  const [presets, setPresets] = useState<StoredPreset<T>[]>(() => loadPresets<T>(storageKey))
  const [selected, setSelected] = useState('')
  const [name, setName] = useState('')

  const save = useCallback(() => {
    // Explicit name wins; otherwise overwrite the currently selected preset.
    const presetName = name.trim() || selected
    if (!presetName) return
    setPresets((prev) => {
      const next = [
        ...prev.filter((p) => p.name !== presetName),
        { name: presetName, values: current, saved_at: Date.now() },
      ].sort((a, b) => a.name.localeCompare(b.name))
      persistPresets(storageKey, next)
      return next
    })
    setSelected(presetName)
    setName('')
  }, [name, selected, current, storageKey])

  const apply = useCallback(
    (presetName: string) => {
      setSelected(presetName)
      if (!presetName) return
      const preset = presets.find((p) => p.name === presetName)
      if (preset) onApply(preset.values)
    },
    [presets, onApply],
  )

  const remove = useCallback(() => {
    if (!selected) return
    setPresets((prev) => {
      const next = prev.filter((p) => p.name !== selected)
      persistPresets(storageKey, next)
      return next
    })
    setSelected('')
  }, [selected, storageKey])

  return (
    <div className="preset-bar">
      <span className="preset-label">Пресеты</span>
      <select
        value={selected}
        onChange={(e) => apply(e.target.value)}
        disabled={disabled}
        aria-label="Выбрать пресет фильтров"
      >
        <option value="">{presets.length ? 'Выбрать…' : 'Нет сохранённых'}</option>
        {presets.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}
          </option>
        ))}
      </select>
      {selected && (
        <button
          type="button"
          className="ghost compact-btn"
          onClick={remove}
          disabled={disabled}
        >
          Удалить
        </button>
      )}
      <input
        type="text"
        className="preset-name"
        placeholder={selected ? `Имя (или обновить «${selected}»)` : 'Название пресета'}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') save()
        }}
        disabled={disabled}
        spellCheck={false}
      />
      <button
        type="button"
        className="ghost compact-btn"
        onClick={save}
        disabled={disabled || (!name.trim() && !selected)}
        title={
          name.trim()
            ? 'Сохранить текущие фильтры как пресет'
            : selected
              ? `Перезаписать пресет «${selected}» текущими фильтрами`
              : 'Введите название пресета'
        }
      >
        Сохранить
      </button>
    </div>
  )
}
