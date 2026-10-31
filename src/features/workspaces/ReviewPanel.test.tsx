import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ReviewPanel } from './ReviewPanel'

afterEach(() => vi.unstubAllGlobals())
const draft = { id: 'd1', kind: 'cover_letter', content: 'Original cover letter', human_edited: false }
const bundle = { company: 'Example', role: 'Engineer', url: 'https://example.com/jobs/1', phase: 'ready_for_review', processing: false, profile_revision: 2, match: { reason: 'Strong Python fit', score: 90, cautions: ['Check location'] }, gaps: ['Missing SQL evidence'], unresolved_questions: ['Can you relocate?'], latest_drafts: [draft], findings: [], reminders: [], analysis_summary: 'Backend role', review_summary: 'Review before submitting' }
const response = (value: unknown) => ({ ok: true, json: async () => value })
it('shows the review package and saves an edited version', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response(bundle)).mockResolvedValueOnce(response({ id: 'd2' })).mockResolvedValueOnce(response({ ...bundle, latest_drafts: [{ ...draft, id: 'd2', content: 'Edited cover letter', human_edited: true }] }))
  vi.stubGlobal('fetch', fetcher)
  render(<ReviewPanel workspaceId="w1" initiallyOpen onSaved={vi.fn().mockResolvedValue(undefined)} />)
  const user = userEvent.setup()
  await screen.findByText('Strong Python fit')
  expect(screen.getByText('Missing SQL evidence')).toBeInTheDocument()
  expect(screen.getByText('Can you relocate?')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open original application' })).toHaveAttribute('href', bundle.url)
  await user.click(screen.getByRole('button', { name: 'Edit cover letter' }))
  await user.clear(screen.getByLabelText('Edit draft text'))
  await user.type(screen.getByLabelText('Edit draft text'), 'Edited cover letter')
  await user.click(screen.getByRole('button', { name: 'Save edited version' }))
  await screen.findByText('Edited cover letter')
  expect(fetcher.mock.calls[1][0]).toBe('/api/workspaces/w1/drafts/d1/edit')
  expect(screen.getByText(/Your edited version · not automatically re-reviewed/)).toBeInTheDocument()
})
it('retains edits after a stale-save conflict', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(bundle)).mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'A newer draft version exists.' }) }))
  render(<ReviewPanel workspaceId="w1" initiallyOpen onSaved={vi.fn()} />)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Edit cover letter' }))
  await user.type(screen.getByLabelText('Edit draft text'), ' My changes')
  await user.click(screen.getByRole('button', { name: 'Save edited version' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Edit draft text')).toHaveValue('Original cover letter My changes')
})
