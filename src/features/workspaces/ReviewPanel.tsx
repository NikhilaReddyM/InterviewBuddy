import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'

type Draft = { id: string; kind: string; content: string; human_edited: boolean; based_on?: string | null }
type Bundle = { company: string; role: string; url: string; phase: string; processing: boolean; profile_revision: number; match: { reason: string; score: number; cautions: string[] } | null; gaps: string[]; unresolved_questions: string[]; latest_drafts: Draft[]; findings: { id: string; draft_id: string; severity: string; message: string }[]; reminders: { id: string; done: number; due_date: string; note: string }[]; analysis_summary: string; review_summary: string }
async function api<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(body) })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Could not load or save this review. Your edits are retained; retry or reload.')
  }
  return response.json() as Promise<T>
}
export function ReviewPanel({ workspaceId, initiallyOpen = false, onSaved }: { workspaceId: string; initiallyOpen?: boolean; onSaved: () => Promise<void> }) {
  const [open, setOpen] = useState(initiallyOpen)
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [editing, setEditing] = useState<Draft | null>(null)
  const [text, setText] = useState('')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const dirty = editing !== null && text !== editing.content
  const base = `/api/workspaces/${workspaceId}`
  useEffect(() => {
    if (!open) return
    let active = true
    api<Bundle>(`${base}/review`).then(value => { if (active) { setBundle(value); setError('') } }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : 'Could not load review.') }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [base, open, revision])
  useEffect(() => {
    if (!dirty) return
    const navigate = (event: Event) => { if (!window.confirm('Discard unsaved draft edits?')) event.preventDefault() }
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', unload)
    window.addEventListener('interviewbuddy:before-navigate', navigate)
    window.addEventListener('interviewbuddy:before-workspace-change', navigate)
    return () => { window.removeEventListener('beforeunload', unload); window.removeEventListener('interviewbuddy:before-navigate', navigate); window.removeEventListener('interviewbuddy:before-workspace-change', navigate) }
  }, [dirty])
  function reload() { setBusy(true); setRevision(value => value + 1) }
  async function save() {
    if (!editing) return
    setBusy(true); setError(''); setNotice('')
    try {
      await api(`${base}/drafts/${editing.id}/edit`, { content: text, request_id: key })
      setEditing(null); setNotice('Your edited version was saved. Earlier drafts and their findings are preserved.')
      reload(); await onSaved()
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not save; your edits are retained.') }
    finally { setBusy(false) }
  }
  return <section className="agent-panel"><div className="career-section-heading"><h3>Application review</h3><Button disabled={busy} variant="secondary" onClick={() => { setBusy(true); setOpen(true); if (open) reload() }}>{open ? 'Refresh review package' : 'Open review package'}</Button></div>
    {open && busy && <p role="status">Loading or saving review…</p>}
    {error && <p className="career-error" role="alert">{error}</p>}{notice && <p role="status" className="career-notice">{notice}</p>}
    {open && bundle && <><p><strong>{bundle.phase.replaceAll('_', ' ')}</strong> · Profile version {bundle.profile_revision}{bundle.processing ? ' · Agents are still running; refresh for the latest results.' : ''}</p>
      {bundle.url && <a className="button button--secondary" href={bundle.url} target="_blank" rel="noreferrer">Open original application</a>}
      {bundle.match && <div className="agent-requirement"><h4>Why this job matched · {bundle.match.score}/100</h4><p>{bundle.match.reason}</p>{bundle.match.cautions.map((caution, index) => <p key={index}>Check: {caution}</p>)}</div>}
      {bundle.analysis_summary && <p>{bundle.analysis_summary}</p>}
      <h4>Gaps and cautions</h4>{bundle.gaps.length ? <ul>{bundle.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul> : <p>No gaps recorded yet.</p>}
      <h4>Unresolved questions</h4><p className="subtle">Questions flagged by the agents. Draft edits do not automatically verify or clear these flags.</p>{bundle.unresolved_questions.length ? <ul>{bundle.unresolved_questions.map((question, index) => <li key={index}>{question}</li>)}</ul> : <p>No unanswered questions recorded yet. Verify the materials before submitting.</p>}
      <h4>Latest drafts</h4>{!bundle.latest_drafts.length && <p>No drafts have been saved. A deferred run is not ready to submit.</p>}
      {bundle.latest_drafts.map(draft => <article className="career-fact" key={draft.id}><h4>{draft.kind.replaceAll('_', ' ')}</h4><p className="subtle">{draft.human_edited ? 'Your edited version · not automatically re-reviewed' : 'Agent/manual draft · check the findings below'}</p><pre className="review-draft-text">{draft.content}</pre>
        <Button variant="secondary" disabled={busy || editing !== null} onClick={() => { setEditing(draft); setText(draft.content); setKey(crypto.randomUUID()); setNotice('') }}>Edit {draft.kind.replaceAll('_', ' ')}</Button>
        {bundle.findings.filter(finding => finding.draft_id === draft.id).map(finding => <p key={finding.id}><strong>{finding.severity}:</strong> {finding.message}</p>)}
        {draft.human_edited && <p className="subtle">Findings on earlier versions remain in draft history. This edit has not been checked by the Reviewer.</p>}
      </article>)}
      {editing && <form onSubmit={event => { event.preventDefault(); void save() }}><div className="field"><label htmlFor="review-draft-edit">Edit draft text</label><textarea id="review-draft-edit" rows={12} maxLength={60000} disabled={busy} required value={text} onChange={event => { setText(event.target.value); setKey(crypto.randomUUID()) }} /></div><div className="actions"><Button type="submit" disabled={busy || !text.trim() || !dirty}>Save edited version</Button><Button variant="secondary" disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard your unsaved draft edits?')) setEditing(null) }}>Cancel edit</Button></div></form>}
      <h4>Review findings</h4>{bundle.review_summary && <p>{bundle.review_summary}</p>}{bundle.findings.map(finding => <p key={finding.id}><strong>{finding.severity}</strong> · {bundle.latest_drafts.some(draft => draft.id === finding.draft_id) ? 'Current draft' : 'Earlier draft'}: {finding.message}</p>)}
      <h4>Review reminders</h4>{bundle.reminders.map(reminder => <div className="workspace-reminder" key={reminder.id}><p>{reminder.due_date} · {reminder.note}{reminder.done ? ' · Done' : ''}</p>{!reminder.done && <Button disabled={busy} variant="secondary" onClick={async () => { setBusy(true); try { await api(`${base}/reminders/${reminder.id}/complete`, {}); reload(); await onSaved(); setNotice('Reminder marked done. This does not mark the application as submitted.') } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update reminder.') } finally { setBusy(false) } }}>Mark review done</Button>}</div>)}
    </>}
  </section>
}
