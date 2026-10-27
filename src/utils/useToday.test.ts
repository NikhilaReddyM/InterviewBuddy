import { act, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useToday } from './useToday'

afterEach(() => vi.useRealTimers())
it('refreshes the calendar date after midnight and cleans up its timer', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 9, 27, 23, 59, 30))
  const hook = renderHook(useToday)
  expect(hook.result.current).toBe('2026-10-27')
  act(() => { vi.advanceTimersByTime(60_000) })
  expect(hook.result.current).toBe('2026-10-28')
  hook.unmount()
  expect(vi.getTimerCount()).toBe(0)
})
