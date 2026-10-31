import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { DiscoverySchedules } from './DiscoverySchedules'

afterEach(() => vi.unstubAllGlobals())
const response = (value: unknown) => ({ ok: true, json: async () => value })
it('creates a paused schedule unless the user explicitly enables it', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response({ id: 's1' })).mockResolvedValueOnce(response([]))
  vi.stubGlobal('fetch', fetcher)
  render(<DiscoverySchedules resumes={[{ id: 'resume', filename: 'Resume.pdf' }]} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Configure schedules' }))
  await user.selectOptions(await screen.findByLabelText('Confirmed resume profile'), 'resume')
  expect(screen.getByLabelText('Enable scheduled discovery using my confirmed profile')).not.toBeChecked()
  await user.click(screen.getByRole('button', { name: 'Save schedule' }))
  await screen.findByText('Schedule saved paused. Enable it when ready.')
  const payload = JSON.parse(fetcher.mock.calls[1][1].body)
  expect(payload.enabled).toBe(false)
  expect(payload.timezone).toBe('America/New_York')
  expect(payload.weekdays).toEqual([0, 1, 2, 3, 4])
})
it('shows next run time and pauses an enabled schedule', async () => {
  const schedule = { id: 's1', name: 'Weekdays', resume_id: 'resume', timezone: 'America/New_York', local_time: '09:00', weekdays: [0, 1, 2, 3, 4], enabled: true, max_applications: 1, revision: 1, next_run_at: '2026-11-02T14:00:00Z', runs: [] }
  const fetcher = vi.fn().mockResolvedValueOnce(response([schedule])).mockResolvedValueOnce(response({ ...schedule, enabled: false })).mockResolvedValueOnce(response([{ ...schedule, enabled: false, next_run_at: null }]))
  vi.stubGlobal('fetch', fetcher)
  render(<DiscoverySchedules resumes={[]} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Configure schedules' }))
  await screen.findByText(/Next run:/)
  await user.click(screen.getByRole('button', { name: 'Pause schedule' }))
  await screen.findByText('Schedule paused. Future runs are disabled.')
  expect(fetcher.mock.calls[1][1].method).toBe('PUT')
  expect(JSON.parse(fetcher.mock.calls[1][1].body).enabled).toBe(false)
  expect(screen.getByText('No run scheduled while paused.')).toBeInTheDocument()
})
