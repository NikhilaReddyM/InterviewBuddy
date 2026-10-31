import { useState } from 'react'
import { Button } from '../../components/Button'

type Preferences = { auto_reminders: boolean; delay_days: number; timezone: string }
export function ReviewPreferences() {
  const [value, setValue] = useState<Preferences | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function request(save = false) {
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch('/api/review-preferences', save ? { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(value) } : undefined)
      const payload = await response.json()
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Could not save reminder preferences.')
      setValue(payload as Preferences)
      if (save) setMessage('Reminder preferences saved. Existing reminder dates are preserved.')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load reminder preferences.') }
    finally { setBusy(false) }
  }
  return <section className="card career-panel"><div className="career-section-heading"><h3>Review reminder preferences</h3><Button disabled={busy} variant="secondary" onClick={() => void request()}>Configure reminders</Button></div><p className="subtle">Automatically remind you when drafts are saved. These settings do not enable job searches or model retries.</p>
    {value && <form onSubmit={event => { event.preventDefault(); void request(true) }}><fieldset className="workspace-fields" disabled={busy}><label className="agent-confirm"><input type="checkbox" checked={value.auto_reminders} onChange={event => setValue({ ...value, auto_reminders: event.target.checked })} />Create review reminders automatically</label><div className="career-preference-grid"><div className="field"><label htmlFor="review-delay">Days after drafts are prepared</label><input id="review-delay" type="number" min={0} max={30} required value={value.delay_days} onChange={event => setValue({ ...value, delay_days: Number(event.target.value) })} /></div><div className="field"><label htmlFor="review-timezone">Reminder timezone</label><input id="review-timezone" required value={value.timezone} onChange={event => setValue({ ...value, timezone: event.target.value })} /></div></div><Button type="submit">Save reminder preferences</Button></fieldset></form>}{error && <p role="alert" className="career-error">{error}</p>}{message && <p role="status">{message}</p>}
  </section>
}
