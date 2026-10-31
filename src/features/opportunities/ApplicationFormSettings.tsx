import { useState } from 'react'
import { Button } from '../../components/Button'

type Settings = { revision: number; auto_prepare: boolean; first_name: string; last_name: string; email: string; phone: string; location: string; linkedin: string; website: string }
const contacts = [{ key: 'first_name', label: 'First name' }, { key: 'last_name', label: 'Last name' }, { key: 'email', label: 'Contact email' }, { key: 'phone', label: 'Phone' }, { key: 'location', label: 'Current city / location' }, { key: 'linkedin', label: 'LinkedIn URL' }, { key: 'website', label: 'Website / portfolio URL' }] as const
export function ApplicationFormSettings() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function request(save = false) {
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch('/api/application-form-preferences', save ? { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(settings) } : undefined)
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save contact settings.')
      setSettings(data); if (save) setMessage('Contact details saved. New scheduled applications will use these confirmed values.')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load contact settings.') } finally { setBusy(false) }
  }
  return <section className="career-panel"><div className="career-section-heading"><h2>Application contact details</h2><Button disabled={busy} variant="secondary" onClick={() => void request()}>Configure application forms</Button></div><p>Confirm details once for employer forms. The browser can upload your resume and fill these details on supported Greenhouse applications. Unknown information is left for you.</p>
    {settings && <form onSubmit={event => { event.preventDefault(); void request(true) }}><fieldset disabled={busy} className="workspace-fields"><div className="career-preference-grid">{contacts.map(field => <div className="field" key={field.key}><label htmlFor={`contact-${field.key}`}>{field.label}</label><input id={`contact-${field.key}`} type={field.key === 'email' ? 'email' : 'text'} maxLength={field.key === 'email' ? 254 : field.key === 'location' ? 300 : field.key === 'phone' ? 100 : ['first_name', 'last_name'].includes(field.key) ? 150 : 1000} value={settings[field.key]} onChange={event => setSettings({ ...settings, [field.key]: event.target.value })} /></div>)}</div>
    <label className="agent-confirm"><input type="checkbox" checked={settings.auto_prepare} onChange={event => setSettings({ ...settings, auto_prepare: event.target.checked })} />Prepare supported employer forms after discovery drafts, including scheduled runs</label><p className="subtle">Browser preparation sends filled details and attachments to the employer site. No applications are submitted. The local backend and browser support must be installed and available.</p><Button type="submit">Save application contact details</Button></fieldset></form>}
    {error && <p role="alert" className="career-error">{error}</p>}{message && <p role="status" className="career-notice">{message}</p>}
  </section>
}
