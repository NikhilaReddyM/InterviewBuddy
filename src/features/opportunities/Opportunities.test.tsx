import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { Opportunities } from './Opportunities'

afterEach(() => vi.unstubAllGlobals())
const response = (value: unknown) => ({ ok: true, json: async () => value })
it('starts autonomous discovery using the selected resume and review date', async () => {
  const batch = { id: 'b1', status: 'queued', created_at: '2026-10-30T12:00:00Z', progress: { events: ['Queued'], items: [] } }
  const fetcher = vi.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([{ id: 'resume', filename: 'Resume.pdf' }])).mockResolvedValueOnce(response([])).mockResolvedValueOnce(response(batch))
  vi.stubGlobal('fetch', fetcher)
  render(<Opportunities onOpenWorkspace={vi.fn()} />)
  const user = userEvent.setup()
  await screen.findByRole('option', { name: 'Resume.pdf' })
  await user.selectOptions(screen.getByLabelText('Resume profile'), 'resume')
  await user.selectOptions(screen.getByLabelText('Maximum applications per run'), '1')
  await user.click(screen.getByRole('button', { name: 'Find opportunities' }))
  await screen.findByText(/Search started/)
  const sent = JSON.parse(fetcher.mock.calls[3][1].body)
  expect(sent.resume_id).toBe('resume')
  expect(sent.max_applications).toBe(1)
  expect(sent.review_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  expect(screen.getByRole('button', { name: 'Discovery in progress…' })).toBeDisabled()
})
it('opens the workspace from a final review reminder', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([{ id: 'r1', workspace_id: 'w1', due_date: '2026-11-01', company: 'Example', role: 'Engineer', note: 'Review application drafts' }]))
  vi.stubGlobal('fetch', fetcher)
  const open = vi.fn()
  render(<Opportunities onOpenWorkspace={open} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Review drafts' }))
  expect(open).toHaveBeenCalledWith('w1')
})
it('explains service failures without losing the discovery form', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))
  render(<Opportunities onOpenWorkspace={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Restart the backend'))
  expect(screen.getByLabelText('Remind me to review on')).toBeInTheDocument()
})
it('hides old errors and disables resume while the worker is running', async () => {
  const batch = { id: 'b1', status: 'running', is_running: true, created_at: '2026-10-30T12:00:00Z', progress: { events: ['Matched 10 of 12 shortlisted roles.'], items: [], error: 'Old rate limit error' } }
  const fetcher = vi.fn().mockResolvedValueOnce(response([batch])).mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([]))
  vi.stubGlobal('fetch', fetcher)
  render(<Opportunities onOpenWorkspace={vi.fn()} />)
  expect(await screen.findByRole('button', { name: 'Batch is running…' })).toBeDisabled()
  expect(screen.queryByText('Old rate limit error')).not.toBeInTheDocument()
})
