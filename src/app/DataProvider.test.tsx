import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { DataProvider } from './DataProvider'
import { useAppData } from './dataContext'
import { createEmptyData } from '../types/defaults'
import { loadData } from '../storage/storage'
import type { StoragePort } from '../storage/storage'

function setup(initial: string | null = null) {
  let raw = initial
  let fail = false
  const storage: StoragePort = {
    getItem: () => raw,
    setItem: (_key, value) => {
      if (fail) throw new DOMException('full', 'QuotaExceededError')
      raw = value
    },
  }
  const wrapper = ({ children }: { children: ReactNode }) => <DataProvider storage={storage}>{children}</DataProvider>
  return { storage, wrapper, setFail: () => { fail = true } }
}
const session = { topic: 'Graphs', area: 'Coding' as const, date: '2026-10-27', plannedMinutes: 60 }

describe('DataProvider', () => {
  it('persists sequential actions, completion and undo, and survives remount', () => {
    const env = setup()
    const hook = renderHook(useAppData, { wrapper: env.wrapper })
    act(() => {
      hook.result.current.dispatch({ type: 'addSession', input: session })
      hook.result.current.dispatch({ type: 'updatePreferences', input: { theme: 'dark' } })
    })
    const id = hook.result.current.data.sessions[0].id
    act(() => { hook.result.current.dispatch({ type: 'completeSession', id, input: { actualMinutes: 80, takeaways: 'DFS', confidence: 4 } }) })
    expect(hook.result.current.data.sessions[0].completion?.actualMinutes).toBe(80)
    act(() => { hook.result.current.dispatch({ type: 'undoCompletion', id }) })
    expect(hook.result.current.data.sessions[0].completion).toBeUndefined()
    hook.unmount()
    const remount = renderHook(useAppData, { wrapper: env.wrapper })
    expect(remount.result.current.data.preferences.theme).toBe('dark')
    expect(remount.result.current.data.sessions[0].topic).toBe('Graphs')
  })
  it('keeps data unchanged on validation or persistence failure', () => {
    const env = setup()
    const { result } = renderHook(useAppData, { wrapper: env.wrapper })
    act(() => { expect(result.current.dispatch({ type: 'addSession', input: { ...session, plannedMinutes: 0 } })).toBe(false) })
    expect(result.current.data.sessions).toHaveLength(0)
    env.setFail()
    act(() => { expect(result.current.dispatch({ type: 'addSession', input: session })).toBe(false) })
    expect(result.current.data.sessions).toHaveLength(0)
    expect(result.current.error).toContain('storage is full')
  })
  it('blocks corrupt data writes until confirmed replacement', () => {
    const env = setup('broken')
    const { result } = renderHook(useAppData, { wrapper: env.wrapper })
    expect(result.current.rawRecovery).toBe('broken')
    act(() => { expect(result.current.dispatch({ type: 'addSession', input: session })).toBe(false) })
    expect(env.storage.getItem('')).toBe('broken')
    act(() => { expect(result.current.replaceData(createEmptyData(), false)).toBe(false) })
    act(() => { expect(result.current.replaceData(createEmptyData(), true)).toBe(true) })
    expect(result.current.blocked).toBe(false)
    expect(loadData(env.storage).status).toBe('ready')
  })
})
