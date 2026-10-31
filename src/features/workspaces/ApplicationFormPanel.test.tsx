import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ApplicationFormPanel } from './ApplicationFormPanel'

afterEach(() => vi.unstubAllGlobals())
const field = { name: 'first_name', label: 'First Name', type: 'input_text', required: true, value: 'Example', choices: [], note: '', origin: 'confirmed_contact' }
const plan = { status: 'local_draft', message: 'Answers saved locally', fields: [field], revision: 1 }
const response = (value: unknown, ok = true) => ({ ok, json: async () => value })
it('saves field edits before allowing browser restoration', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response(plan)).mockResolvedValueOnce(response({ ...plan, revision: 2, fields: [{ ...field, value: 'Changed' }] })).mockResolvedValueOnce(response({ ...plan, revision: 2, message: 'Opening browser' }))
  vi.stubGlobal('fetch', fetcher)
  render(<ApplicationFormPanel workspaceId="workspace" />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Load saved application form' }))
  const input = await screen.findByLabelText('First Name · Required by employer')
  await user.clear(input); await user.type(input, 'Changed')
  expect(screen.getByRole('button', { name: 'Review application in browser' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Save application answers' }))
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ revision: 1, values: { first_name: 'Changed' } })
  await user.click(screen.getByRole('button', { name: 'Review application in browser' }))
  expect(fetcher.mock.calls[2][0]).toBe('/api/workspaces/workspace/application-form/open')
  expect(await screen.findByRole('status')).toHaveTextContent('Opening browser')
})
it('retains unsaved answers when a stale version is rejected', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(plan)).mockResolvedValueOnce(response({ detail: 'Application form changed. Reload before saving.' }, false)))
  render(<ApplicationFormPanel workspaceId="workspace" />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Load saved application form' }))
  const input = await screen.findByLabelText('First Name · Required by employer')
  await user.clear(input); await user.type(input, 'My unsaved answer')
  await user.click(screen.getByRole('button', { name: 'Save application answers' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Application form changed')
  expect(input).toHaveValue('My unsaved answer')
})
