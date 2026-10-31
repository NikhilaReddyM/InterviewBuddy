import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'

type FormField = { name: string; label: string; type: string; required: boolean; value: string | null; choices: { value: string; label: string }[]; note: string; origin: string }
type Plan = { status: string; message?: string; fields: FormField[]; revision: number; missing_required?: string[]; browser_results?: { name: string; label: string; status: string; reason?: string }[]; remote_draft_url?: string | null; schema_changed?: boolean; answer_generation_error?: string | null; generation_warnings?: string[] }
async function request<T>(url: string, body?: unknown, method = 'POST'): Promise<T> {
  const result = await fetch(url, body === undefined ? undefined : { method, headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(body) })
  const value = await result.json()
  if (!result.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Could not update the application form. Your saved answers are preserved.')
  return value as T
}
export function ApplicationFormPanel({ workspaceId }: { workspaceId: string }) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const base = `/api/workspaces/${workspaceId}/application-form`
  const dirty = !!plan && plan.fields.some(field => field.type !== 'input_file' && (values[field.name] ?? '') !== (field.value ?? ''))
  useEffect(() => {
    if (!dirty) return
    const navigate = (event: Event) => { if (!window.confirm('Discard unsaved application answers?')) event.preventDefault() }
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', unload)
    window.addEventListener('interviewbuddy:before-navigate', navigate)
    window.addEventListener('interviewbuddy:before-workspace-change', navigate)
    return () => { window.removeEventListener('beforeunload', unload); window.removeEventListener('interviewbuddy:before-navigate', navigate); window.removeEventListener('interviewbuddy:before-workspace-change', navigate) }
  }, [dirty])
  function loaded(value: Plan) { setPlan(value); setValues(Object.fromEntries(value.fields.map(field => [field.name, field.value ?? '']))) }
  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await work() } catch (failure) { setError(failure instanceof Error ? failure.message : 'Application form operation failed.') } finally { setBusy(false) }
  }
  return <section className="application-form-panel"><div className="career-section-heading"><div><p className="eyebrow">EMPLOYER APPLICATION</p><h3>Prepare now. Review and submit later.</h3></div></div>
    <p>Greenhouse applications can be restored in a dedicated browser with your saved answers and uploaded resume. Missing answers stay blank. You review and press Submit yourself.</p>
    <div className="actions"><Button disabled={busy || dirty} variant="secondary" onClick={() => void action(async () => loaded(await request<Plan>(base)))}>Load saved application form</Button><Button disabled={busy || dirty} onClick={() => void action(async () => loaded(await request<Plan>(base + '/prepare', {})))}>Prepare / refresh employer form</Button></div>
    {busy && <p role="status">Preparing the application…</p>}{error && <p role="alert" className="career-error">{error}</p>}{notice && <p role="status" className="career-notice">{notice}</p>}
    {plan && <><p><strong>{plan.status.replaceAll('_', ' ')}</strong></p><p>{plan.message}</p>{plan.answer_generation_error && <p className="career-notice">{plan.answer_generation_error}</p>}{plan.generation_warnings?.map((warning, i) => <p key={i} className="subtle">{warning}</p>)}{plan.schema_changed && <p className="career-notice">The employer changed its fields. Check the refreshed answers before opening.</p>}
      {!!plan.fields.length && <><form onSubmit={event => { event.preventDefault(); void action(async () => {
        loaded(await request<Plan>(base, { revision: plan.revision, values: Object.fromEntries(plan.fields.filter(field => field.type !== 'input_file' && (values[field.name] ?? '') !== (field.value ?? '')).map(field => [field.name, values[field.name] || null])) }, 'PUT'))
        setNotice('Answers saved. Use Review application to restore them in the employer form.')
      }) }}><div className="career-preference-grid">{plan.fields.map(field => <div className="field" key={field.name}><label htmlFor={`application-${field.name}`}>{field.label}{field.required ? ' · Required by employer' : ''}</label>
        {field.type === 'input_file' ? <p>{field.value || 'Select this attachment manually in the employer browser.'}</p> : field.choices.length ? <select id={`application-${field.name}`} disabled={busy} value={values[field.name] ?? ''} onChange={event => setValues({ ...values, [field.name]: event.target.value })}><option value="">Leave unanswered</option>{field.choices.map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select> : <textarea rows={field.type === 'textarea' ? 5 : 2} id={`application-${field.name}`} maxLength={60000} disabled={busy} value={values[field.name] ?? ''} onChange={event => setValues({ ...values, [field.name]: event.target.value })} />}
        {field.note && <p className="field-hint">{field.note}</p>}</div>)}</div><Button disabled={busy || !dirty} type="submit">Save application answers</Button></form>
      <div className="actions"><Button disabled={busy || dirty} onClick={() => void action(async () => { const value = await request<Plan>(base + '/open', {}); setPlan(value); setNotice(value.message ?? 'Opening your application browser.') })}>Review application in browser</Button><Button disabled={busy || dirty} variant="secondary" onClick={() => void action(async () => loaded(await request<Plan>(base)))}>Refresh form status</Button></div>
      <p className="subtle">Saved answers survive restarts. Without a confirmed employer-side draft, reopen from InterviewBuddy to refill the form. Browser-only edits are not copied back here; save changes here if you need to restore them later. Login, verification, declarations and unsupported fields may need your attention.</p>
      {!!plan.browser_results?.length && <details className="career-details"><summary>Browser preparation results</summary>{plan.browser_results.map(result => <p key={result.name}>{result.label}: {result.status.replaceAll('_', ' ')}{result.reason ? ` — ${result.reason}` : ''}</p>)}</details>}
      {plan.remote_draft_url && <a href={plan.remote_draft_url} target="_blank" rel="noreferrer">Open employer’s saved draft</a>}
      </>}
    </>}
  </section>
}
