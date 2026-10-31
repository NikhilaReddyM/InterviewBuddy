import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { EmailDigest } from './EmailDigest'

afterEach(() => vi.unstubAllGlobals())
const settings = { enabled: false, recipient: '', timezone: 'America/New_York', local_time: '17:00', weekdays: [0, 1, 2, 3, 4], lookahead_days: 0, app_base_url: 'http://localhost:5173', revision: 0, next_run_at: null, smtp: { configured: true, missing: [], sender: 'sender@example.test' }, deliveries: [], slots: [] }
const response = (value: unknown) => ({ ok: true, json: async () => value })
it('previews while disabled without sending email', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response(settings)).mockResolvedValueOnce(response({ id: 'preview', recipient: '', sender: settings.smtp.sender, subject: 'Application reviews', text: 'One pending draft', items: [{}] }))
  vi.stubGlobal('fetch', fetcher)
  render(<EmailDigest />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Configure email digest' }))
  expect(await screen.findByLabelText('Enable email delivery and scheduled digests to this recipient')).not.toBeChecked()
  await user.click(screen.getByRole('button', { name: 'Preview pending digest' }))
  await screen.findByText('One pending draft')
  expect(screen.getByRole('button', { name: 'Send this digest now' })).toBeDisabled()
  expect(fetcher.mock.calls.map(call => call[0])).toEqual(['/api/email-digest', '/api/email-digest/preview'])
})
it('requires an explicit send click after preview and disables repeated send', async () => {
  const enabled = { ...settings, enabled: true, recipient: 'reviewer@example.test', revision: 1 }
  const fetcher = vi.fn().mockResolvedValueOnce(response(enabled)).mockResolvedValueOnce(response({ id: 'preview', recipient: enabled.recipient, sender: enabled.smtp.sender, subject: 'Reviews', text: 'Pending drafts', items: [{}] })).mockResolvedValueOnce(response({ id: 'delivery', status: 'sent', message: 'Accepted by SMTP.' })).mockResolvedValueOnce(response(enabled))
  vi.stubGlobal('fetch', fetcher)
  render(<EmailDigest />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Configure email digest' }))
  await user.click(await screen.findByRole('button', { name: 'Preview pending digest' }))
  await user.click(await screen.findByRole('button', { name: 'Send this digest now' }))
  await screen.findByText('sent: Accepted by SMTP.')
  expect(fetcher.mock.calls[2][0]).toBe('/api/email-digest/send')
  expect(screen.getByRole('button', { name: 'Send this digest now' })).toBeDisabled()
})
it('retries a failed scheduled email directly from delivery history', async () => {
  const enabled = { ...settings, enabled: true, recipient: 'reviewer@example.test', revision: 1, deliveries: [{ id: 'failed', preview_id: 'scheduled-preview', status: 'failed', message: 'Not accepted.' }] }
  const fetcher = vi.fn().mockResolvedValueOnce(response(enabled)).mockResolvedValueOnce(response({ id: 'failed', preview_id: 'scheduled-preview', status: 'sent', message: 'Accepted.' })).mockResolvedValueOnce(response({ ...enabled, deliveries: [{ ...enabled.deliveries[0], status: 'sent' }] }))
  vi.stubGlobal('fetch', fetcher)
  render(<EmailDigest />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Configure email digest' }))
  await user.click(await screen.findByRole('button', { name: 'Retry failed email' }))
  await screen.findByText('sent: Accepted.')
  expect(fetcher.mock.calls[1][0]).toBe('/api/email-digest/retry')
  expect(JSON.parse(fetcher.mock.calls[1][1].body).preview_id).toBe('scheduled-preview')
})
