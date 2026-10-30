import { act, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CooldownStatus } from './CooldownStatus'
import { remainingCooldown } from './cooldown'

afterEach(() => vi.useRealTimers())
it('counts down and switches to manual resume guidance', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-30T20:00:00Z'))
  const seconds = Date.now() / 1000
  render(<CooldownStatus until={seconds + 65} />)
  expect(screen.getByRole('timer')).toHaveTextContent('1m 5s')
  act(() => vi.advanceTimersByTime(5000))
  expect(screen.getByRole('timer')).toHaveTextContent('1m 0s')
  act(() => vi.advanceTimersByTime(60000))
  expect(screen.getByText('Recorded cooldown has ended')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Click Resume saved batch')
})
it('uses the server clock and shows manual retry guidance', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-30T20:00:00Z'))
  render(<CooldownStatus until={1060} serverTime={1000} />)
  expect(screen.getByRole('timer')).toHaveTextContent('1m 0s')
  expect(screen.getByRole('status')).toHaveTextContent('Automatic retries are off')
  act(() => vi.advanceTimersByTime(60000))
  expect(screen.getByRole('status')).toHaveTextContent('Click Resume saved batch')
})
it('formats long cooldowns without negative values', () => {
  expect(remainingCooldown(3661, 0)).toBe('1h 1m 1s')
  expect(remainingCooldown(0, 100)).toBe('0s')
})
