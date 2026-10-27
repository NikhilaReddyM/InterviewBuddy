import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { AppData } from '../types/models'
import { createEmptyData } from '../types/defaults'
import { applyDataAction } from './dataActions'
import type { DataAction } from './dataActions'
import { loadData, saveData, validateData, replaceData as persistReplacement } from '../storage/storage'
import type { StoragePort } from '../storage/storage'
import { DataContext } from './dataContext'


export function DataProvider({ children, storage }: { children: ReactNode; storage?: StoragePort }) {
  const [initial] = useState(() => loadData(storage))
  const current = useRef(initial.status === 'error' ? createEmptyData() : initial.data)
  const raw = useRef(initial.raw)
  const locked = useRef(initial.status === 'error')
  const [data, setData] = useState(() => initial.status === 'error' ? createEmptyData() : initial.data)
  const [error, setError] = useState<string | null>(initial.status === 'error' ? initial.error.message : null)
  const [blocked, setBlocked] = useState(initial.status === 'error')
  const [rawRecovery, setRawRecovery] = useState<string | null>(initial.status === 'error' ? initial.raw : null)

  function commit(next: AppData, replacement = false, confirmed = false): boolean {
    try {
      if (locked.current && !replacement) throw new Error('Resolve the storage error before making changes.')
      const validated = validateData(next)
      const saved = replacement
        ? persistReplacement(validated, raw.current, confirmed, storage)
        : saveData(validated, raw.current, storage)
      // Publish only after persistence succeeds. Refs also preserve sequential batched actions.
      raw.current = saved
      current.current = validated
      locked.current = false
      setData(current.current)
      setBlocked(false)
      setRawRecovery(null)
      setError(null)
      return true
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The change could not be saved.')
      return false
    }
  }

  function dispatch(action: DataAction): boolean {
    try { return commit(applyDataAction(current.current, action)) }
    catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Invalid change.')
      return false
    }
  }

  function reload() {
    const loaded = loadData(storage)
    raw.current = loaded.raw
    locked.current = loaded.status === 'error'
    setBlocked(locked.current)
    setRawRecovery(loaded.status === 'error' ? loaded.raw : null)
    setError(loaded.status === 'error' ? loaded.error.message : null)
    if (loaded.status !== 'error') {
      current.current = loaded.data
      setData(loaded.data)
    }
  }

  return <DataContext.Provider value={{
    data, error, blocked, rawRecovery, dispatch, reload,
    replaceData: (next, confirmed) => commit(next, true, confirmed),
  }}>{children}</DataContext.Provider>
}
