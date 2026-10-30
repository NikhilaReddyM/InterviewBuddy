import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AgentFlowPanel } from './AgentFlowPanel'

afterEach(() => vi.unstubAllGlobals())
const paused = { id: 'run-1', checkpoint_id: 'checkpoint-1', paused: true, next: ['clarification'], state: { phase: 'coordinating', decision: { action: 'clarify', reason: 'Location preference is missing.', questions: ['Are you open to hybrid work?'] }, events: ['Analyst checked requirements.'] } }
const finished = { ...paused, checkpoint_id: 'checkpoint-2', paused: false, next: [], state: { phase: 'ready_for_review', decision: { action: 'finish', reason: 'Materials are ready for your review.', questions: [] }, package: { cover_letter: [{ text: 'I build Python services.', source_ids: ['fact-1'] }], resume_suggestions: [], screening_answers: [] }, context: { facts: { 'fact-1': { text: 'Built Python services', evidence: 'Built Python services' } } }, review: { summary: 'Claims are supported.', findings: [] } } }
const response = (value: unknown) => ({ ok: true, json: async () => value })
it('starts, asks for explicit answers, and displays the reviewed package', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response(paused)).mockResolvedValueOnce(response(finished))
  vi.stubGlobal('fetch', fetcher)
  const onSaved = vi.fn().mockResolvedValue(undefined)
  render(<AgentFlowPanel workspaceId="w1" runs={[]} onSaved={onSaved} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Prepare application' }))
  await screen.findByText('A few details are needed')
  await user.type(screen.getByLabelText('Are you open to hybrid work?'), 'Yes')
  expect(screen.getByRole('button', { name: 'Save answers and continue' })).toBeDisabled()
  await user.click(screen.getByLabelText('Use these answers in my application drafts'))
  await user.click(screen.getByRole('button', { name: 'Save answers and continue' }))
  await screen.findByText('Ready for your review')
  expect(screen.getByText('I build Python services.')).toBeInTheDocument()
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ checkpoint_id: 'checkpoint-1', answers: ['Yes'] })
  expect(onSaved).toHaveBeenCalledTimes(2)
})
it('reopens a failed run and retries its pending step', async () => {
  const failed = { ...paused, paused: false, error: 'Provider timeout', next: ['reviewer'], state: { phase: 'drafted' } }
  const fetcher = vi.fn().mockResolvedValueOnce(response(failed)).mockResolvedValueOnce(response(finished))
  vi.stubGlobal('fetch', fetcher)
  render(<AgentFlowPanel workspaceId="w1" runs={[{ id: 'run-1', workflow: 'application_v1' }]} onSaved={vi.fn().mockResolvedValue(undefined)} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Open agent run 1' }))
  await screen.findByText('Provider timeout')
  await user.click(screen.getByRole('button', { name: 'Retry failed step' }))
  await waitFor(() => expect(screen.getByText('Ready for your review')).toBeInTheDocument())
  expect(fetcher.mock.calls[1][0]).toContain('/agent-runs/run-1/retry')
})
