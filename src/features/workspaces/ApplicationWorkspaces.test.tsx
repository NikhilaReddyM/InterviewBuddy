import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ApplicationWorkspaces } from './ApplicationWorkspaces'

afterEach(() => vi.unstubAllGlobals())
const workspace = { id: 'w1', company: 'Example', role: 'Engineer', description: 'Build APIs', url: '', profile_snapshot: { profile_revision: 2 }, drafts: [], findings: [], reminders: [], runs: [] }
const response = (value: unknown) => ({ ok: true, json: async () => value })
it('opens a persisted workspace and saves a new draft', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response([workspace])).mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(response(workspace)).mockResolvedValueOnce(response({ id: 'draft' }))
    .mockResolvedValueOnce(response({ ...workspace, drafts: [{ id: 'draft', kind: 'cover_letter', content: 'My draft', profile_snapshot_id: 'snapshot' }] }))
  vi.stubGlobal('fetch', fetcher)
  render(<ApplicationWorkspaces />)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Example · Engineer' }))
  await screen.findByText(/Profile version 2/)
  await user.type(screen.getByLabelText('New draft version'), 'My draft')
  await user.click(screen.getByRole('button', { name: 'Save draft version' }))
  await screen.findByText('New draft version saved.')
  expect(JSON.parse(fetcher.mock.calls[3][1].body).content).toBe('My draft')
  expect(screen.getByLabelText('New draft version')).toHaveValue('')
})
it('keeps draft text after a failed save', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response([workspace])).mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(response(workspace)).mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'Backend unavailable. Retry.' }) })
  vi.stubGlobal('fetch', fetcher)
  render(<ApplicationWorkspaces />)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Example · Engineer' }))
  await user.type(await screen.findByLabelText('New draft version'), 'Keep this draft')
  await user.click(screen.getByRole('button', { name: 'Save draft version' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Backend unavailable. Retry.'))
  expect(screen.getByLabelText('New draft version')).toHaveValue('Keep this draft')
})
