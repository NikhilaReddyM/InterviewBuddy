import { useState } from 'react'
import { Button } from '../../components/Button'

type Config = { enabled: boolean; recipient: string; timezone: string; local_time: string; weekdays: number[]; lookahead_days: number; app_base_url: string; revision: number }
type Delivery = { id?: string; preview_id?: string; status: string; message: string; created_at?: string; last_attempt_at?: string; attempt_count?: number }
type Settings = Config & { next_run_at: string | null; smtp: { configured: boolean; missing: string[]; sender: string }; deliveries?: Delivery[]; slots?: { scheduled_for: string; status: string; message: string }[] }
type Preview = { id: string; recipient: string; sender: string; subject: string; text: string; items: unknown[] }
const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
function fields(value: Config): Config {
  return { enabled: value.enabled, recipient: value.recipient, timezone: value.timezone, local_time: value.local_time, weekdays: value.weekdays, lookahead_days: value.lookahead_days, app_base_url: value.app_base_url, revision: value.revision }
}
async function request<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  const response = await fetch('/api/email-digest' + path, body === undefined ? undefined : { method, headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(body) })
  const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Check the email address, timezone, and app URL, then retry.')
  return payload as T
}
export function EmailDigest() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [form, setForm] = useState<Config | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [delivery, setDelivery] = useState<Delivery | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const dirty = !!(form && settings && JSON.stringify(fields(form)) !== JSON.stringify(fields(settings)))
  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await work() } catch (failure) { setError(failure instanceof Error ? failure.message : 'Email operation failed. Check delivery history before retrying.') } finally { setBusy(false) }
  }
  async function load() {
    const value = await request<Settings>('')
    setSettings(value); setForm(fields(value)); setPreview(null); setDelivery(null)
  }
  async function send(retry = false, requestedPreviewId?: string) {
    const previewId = requestedPreviewId ?? preview?.id ?? delivery?.preview_id
    if (!previewId) return
    const result = await request<Delivery>(retry ? '/retry' : '/send', { preview_id: previewId })
    setDelivery(result)
    const latest = await request<Settings>('')
    setSettings(latest)
  }
  return <section className="card career-panel"><div className="career-section-heading"><h2>Email review digest</h2><Button disabled={busy} variant="secondary" onClick={() => { if (dirty && !window.confirm('Discard unsaved email settings?')) return; void action(load) }}>{settings ? 'Refresh email settings' : 'Configure email digest'}</Button></div>
    <p>Receive a summary of pending application reviews with links to drafts and original job listings. Email is off by default. No email is sent until you configure delivery and explicitly enable it.</p>
    {settings && form && <><p>{settings.smtp.configured ? `Delivery account configured: ${settings.smtp.sender}` : 'An email delivery account must be configured in the backend before sending.'}</p>{!settings.smtp.configured && <details className="career-details"><summary>Delivery setup details</summary><p>Set SMTP delivery credentials in backend/.env and restart. Missing settings: {settings.smtp.missing.join(', ')}. Credentials are never entered into this page.</p></details>}
      <form onSubmit={event => { event.preventDefault(); void action(async () => { const value = await request<Settings>('', fields(form), 'PUT'); setSettings(previous => ({ ...value, deliveries: previous?.deliveries, slots: previous?.slots })); setForm(fields(value)); setPreview(null); setDelivery(null); setNotice(value.enabled ? 'Email digest enabled. Check the next delivery time below.' : 'Email digest saved disabled. No scheduled emails will be sent.') }) }}><fieldset className="workspace-fields" disabled={busy}><div className="career-preference-grid"><div className="field"><label htmlFor="digest-recipient">Send digest to</label><input id="digest-recipient" type="email" required={form.enabled} maxLength={254} value={form.recipient} onChange={event => setForm({ ...form, recipient: event.target.value })} /></div><div className="field"><label htmlFor="digest-time">Email at</label><input id="digest-time" type="time" required value={form.local_time} onChange={event => setForm({ ...form, local_time: event.target.value })} /></div><div className="field"><label htmlFor="digest-zone">Email timezone</label><input id="digest-zone" required value={form.timezone} onChange={event => setForm({ ...form, timezone: event.target.value })} /></div><div className="field"><label htmlFor="digest-lookahead">Include reviews due within (days)</label><input id="digest-lookahead" type="number" min={0} max={7} required value={form.lookahead_days} onChange={event => setForm({ ...form, lookahead_days: Number(event.target.value) })} /><p className="field-hint">0 includes overdue and today’s reviews. Use 1 to include tomorrow.</p></div><div className="field"><label htmlFor="digest-app-url">InterviewBuddy app URL</label><input id="digest-app-url" type="url" required value={form.app_base_url} onChange={event => setForm({ ...form, app_base_url: event.target.value })} /><p className="field-hint">Localhost links work only on the computer running the app.</p></div></div><fieldset className="schedule-days"><legend>Email on</legend>{days.map((day, index) => <label key={day}><input type="checkbox" checked={form.weekdays.includes(index)} onChange={event => setForm({ ...form, weekdays: event.target.checked ? [...form.weekdays, index].sort() : form.weekdays.filter(value => value !== index) })} />{day}</label>)}</fieldset><label className="agent-confirm"><input type="checkbox" checked={form.enabled} onChange={event => setForm({ ...form, enabled: event.target.checked })} />Enable email delivery and scheduled digests to this recipient</label><Button type="submit" disabled={!form.weekdays.length}>Save email settings</Button></fieldset></form>
      <p>{settings.next_run_at ? `Next digest: ${new Date(settings.next_run_at).toLocaleString(undefined, { timeZone: settings.timezone, timeZoneName: 'short' })}` : 'Scheduled email is disabled.'}</p><p className="subtle">Only reviews with saved drafts are included. Empty digests are skipped. The backend must stay running. This does not change model retry settings.</p>
      <Button disabled={busy || dirty} variant="secondary" onClick={() => void action(async () => { setPreview(await request<Preview>('/preview', {})); setDelivery(null) })}>Preview pending digest</Button>{dirty && <p className="subtle">Save the settings before creating or sending a preview.</p>}
      {preview && <section className="career-fact"><h3>Digest preview</h3><p>To: {preview.recipient || 'Not configured'}</p><p>From: {preview.sender || 'Not configured'}</p><strong>{preview.subject}</strong><pre className="review-draft-text">{preview.text}</pre><Button disabled={busy || dirty || !settings.enabled || !settings.smtp.configured || !preview.items.length || delivery?.status === 'sent' || delivery?.status === 'unknown' || delivery?.status === 'sending'} onClick={() => void action(() => send())}>Send this digest now</Button></section>}
      {delivery && <div className="career-notice" role="status"><p>{delivery.status}: {delivery.message}</p>{delivery.status === 'failed' && <Button disabled={busy || dirty} variant="secondary" onClick={() => void action(() => send(true))}>Retry this failed email</Button>}</div>}
      <details className="career-details"><summary>Delivery history</summary>{!settings.deliveries?.length && !settings.slots?.length && <p>No email deliveries recorded.</p>}{settings.deliveries?.map(item => <p key={item.id}>{item.last_attempt_at || item.created_at ? new Date((item.last_attempt_at || item.created_at)!).toLocaleString() : ''} · {item.attempt_count ? `Attempts: ${item.attempt_count} · ` : ''} <strong>{item.status}</strong>: {item.message}{item.status === 'failed' && item.preview_id && <Button variant="secondary" disabled={busy || dirty || !settings.enabled || !settings.smtp.configured} onClick={() => void action(() => send(true, item.preview_id))}>Retry failed email</Button>}</p>)}{settings.slots?.map(slot => <p key={slot.scheduled_for}>{new Date(slot.scheduled_for).toLocaleString()} · Scheduled digest: {slot.status} · {slot.message}</p>)}</details>
    </>}
    {error && <p role="alert" className="career-error">{error}</p>}{notice && <p role="status" className="career-notice">{notice}</p>}
  </section>
}
