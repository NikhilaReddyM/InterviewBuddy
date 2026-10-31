import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { JobCatalog } from './JobCatalog'

afterEach(() => vi.unstubAllGlobals())
it('browses US hybrid jobs without starting discovery or model calls', async () => {
  const job = { candidate_id: 'one', source: 'ashby:ramp', company: 'Ramp', role: 'Senior Engineer', location: 'New York, USA', workplace: 'hybrid', description: 'Build APIs', url: 'https://example.com/job', retrieved_at: '2026-10-30T12:00:00Z' }
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [job], total_matches: 1, limited: false, sources: [{ source: 'ashby:ramp', count: 10, status: 'available' }], errors: [], model_calls: 0 }) })
  vi.stubGlobal('fetch', fetcher)
  render(<JobCatalog resumes={[]} onSaved={vi.fn()} />)
  const user = userEvent.setup()
  await user.selectOptions(screen.getByLabelText('Work arrangement'), 'hybrid')
  await user.click(screen.getByRole('button', { name: 'Browse jobs — no AI' }))
  await screen.findByText(/No model calls were made/)
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(fetcher.mock.calls[0][0]).toContain('/api/job-catalog?')
  expect(fetcher.mock.calls[0][0]).toContain('workplace=hybrid')
  expect(screen.getByRole('link', { name: 'Original application' })).toHaveAttribute('href', job.url)
  expect(screen.getByRole('button', { name: 'Save job for later' })).toBeDisabled()
})
it('saves a public listing for later without starting an agent', async () => {
  const job = { candidate_id: 'one', source: 'ashby:ramp', company: 'Ramp', role: 'Senior Engineer', location: 'New York, USA', workplace: 'hybrid', description: 'Build APIs', url: 'https://example.com/job', retrieved_at: '2026-10-30T12:00:00Z' }
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ jobs: [job], total_matches: 1, sources: [{ source: 'ashby:ramp', count: 1, status: 'available' }], errors: [], model_calls: 0 }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'saved-workspace' }) })
  vi.stubGlobal('fetch', fetcher)
  vi.stubGlobal('crypto', { subtle: { digest: vi.fn().mockResolvedValue(new Uint8Array([1, 2, 3]).buffer) } })
  const open = vi.fn()
  render(<JobCatalog resumes={[{ id: 'resume', filename: 'Resume.pdf' }]} onSaved={open} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Browse jobs — no AI' }))
  await user.selectOptions(await screen.findByLabelText('Confirmed profile for saving jobs'), 'resume')
  await user.click(screen.getByRole('button', { name: 'Save job for later' }))
  await user.click(await screen.findByRole('button', { name: 'Open saved workspace' }))
  expect(open).toHaveBeenCalledWith('saved-workspace')
  expect(fetcher.mock.calls[1][0]).toBe('/api/workspaces')
  expect(JSON.parse(fetcher.mock.calls[1][1].body).request_id).toBe('catalog:010203')
  expect(fetcher.mock.calls.some(call => String(call[0]).includes('agent-runs'))).toBe(false)
})
