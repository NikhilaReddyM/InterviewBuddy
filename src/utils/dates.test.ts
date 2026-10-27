import { expect, it } from 'vitest'
import { addDays, getWeekStart, getWeekDates, getEffectiveAvailability } from './dates'
import { createEmptyData } from '../types/defaults'

it('uses Monday-start weeks across years and Sunday boundaries', () => {
  expect(getWeekStart('2027-01-01')).toBe('2026-12-28')
  expect(getWeekStart('2026-11-01')).toBe('2026-10-26')
  expect(getWeekDates('2026-11-01')).toEqual(['2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-10-31', '2026-11-01'])
})
it('adds calendar days across daylight-saving and leap-year boundaries', () => {
  expect(addDays('2026-11-01', 1)).toBe('2026-11-02')
  expect(addDays('2028-02-28', 1)).toBe('2028-02-29')
  expect(addDays('2026-03-08', -1)).toBe('2026-03-07')
})
it('honors zero overrides and weekday/weekend defaults', () => {
  const data = createEmptyData()
  expect(getEffectiveAvailability('2026-10-27', data)).toBe(150)
  expect(getEffectiveAvailability('2026-10-31', data)).toBe(0)
  data.availabilityOverrides['2026-10-27'] = 0
  expect(getEffectiveAvailability('2026-10-27', data)).toBe(0)
})
