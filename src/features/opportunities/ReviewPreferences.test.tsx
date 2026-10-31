import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ReviewPreferences } from './ReviewPreferences'

afterEach(() => vi.unstubAllGlobals())
it('loads and saves reminder preferences separately from agent execution', async () => {
  const value = { auto_reminders: true, delay_days: 1, timezone: 'America/New_York' }
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => value })
  vi.stubGlobal('fetch', fetcher)
  render(<ReviewPreferences />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Configure reminders' }))
  await user.click(await screen.findByLabelText('Create review reminders automatically'))
  await user.click(screen.getByRole('button', { name: 'Save reminder preferences' }))
  await screen.findByText(/Reminder preferences saved/)
  expect(fetcher.mock.calls[1][1].method).toBe('PUT')
  expect(JSON.parse(fetcher.mock.calls[1][1].body).auto_reminders).toBe(false)
})
