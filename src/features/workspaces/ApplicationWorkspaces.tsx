import { useEffect, useState } from 'react'
import { AgentFlowPanel } from './AgentFlowPanel'
import { Button } from '../../components/Button'
import '../career-profile/career-profile.css'

type Workspace = { previous_workspace_id?: string | null; id: string; company: string; role: string; description: string; url: string; profile_revision?: number }
type Draft = { id: string; kind: string; content: string; profile_snapshot_id: string }
type Reminder = { id: string; due_date: string; note: string; done: number }
type Run = { id: string; checkpoint_id: string; paused: boolean; state: { phase?: string; instructions?: string } }
type Detail = Workspace & { profile_snapshot: { profile_revision: number }; drafts: Draft[]; findings: { id: string; draft_id: string; severity: string; message: string }[]; reminders: Reminder[]; runs: { id: string; workflow?: string }[] }
type Resume = { id: string; filename: string }
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/workspaces${path}`, body === undefined ? undefined : { method: 'POST', headers: { 'X-InterviewBuddy': 'local', 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: unknown }
    throw new Error(response.status === 404 ? 'Workspace service not found. Restart the backend and reload.' : typeof data.detail === 'string' ? data.detail : 'Could not save. Your entries remain available; please retry.')
  }
  return response.json() as Promise<T>
}
const id = () => crypto.randomUUID()

export function ApplicationWorkspaces({ initialWorkspaceId }: { initialWorkspaceId?: string } = {}) {
  const [items, setItems] = useState<Workspace[]>([])
  const [resumes, setResumes] = useState<Resume[]>([])
  const [detail, setDetail] = useState<Detail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reload, setReload] = useState(0)
  const [job, setJob] = useState({ resume_id: '', company: '', role: '', description: '', url: '', request_id: id() })
  const [draft, setDraft] = useState({ kind: 'cover_letter', content: '', request_id: id() })
  const [finding, setFinding] = useState({ draft_id: '', severity: 'warning', message: '', request_id: id() })
  const [reminder, setReminder] = useState({ due_date: '', note: '', request_id: id() })
  const [run, setRun] = useState<Run | null>(null)
  const [instructions, setInstructions] = useState('')
  const [runKey, setRunKey] = useState(id)
  useEffect(() => {
    let active = true
    Promise.all([api<Workspace[]>(''), fetch('/api/resumes').then(async response => { if (!response.ok) throw new Error('Could not load resumes. Check the backend.'); return response.json() as Promise<Resume[]> })]).then(([workspaces, saved]) => {
      if (active) { setItems(workspaces); setResumes(saved) }
    }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : 'Could not load workspaces.') })
    return () => { active = false }
  }, [reload])
  useEffect(() => {
    if (!initialWorkspaceId) return
    let active = true
    api<Detail>(`/${initialWorkspaceId}`).then(value => { if (active) setDetail(value) }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : 'Could not open workspace.') })
    return () => { active = false }
  }, [initialWorkspaceId])
  const hasEdits = !!(job.company || job.role || job.description || job.url || draft.content || finding.message || reminder.note || reminder.due_date || instructions)
  useEffect(() => {
    if (!hasEdits) return
    const navigate = (event: Event) => { if (!window.confirm('Discard unsaved workspace entries?')) event.preventDefault() }
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('interviewbuddy:before-navigate', navigate)
    window.addEventListener('beforeunload', unload)
    return () => { window.removeEventListener('interviewbuddy:before-navigate', navigate); window.removeEventListener('beforeunload', unload) }
  }, [hasEdits])
  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await work() } catch (failure) { setError(failure instanceof Error ? failure.message : 'Request failed.') } finally { setBusy(false) }
  }
  async function refresh(workspaceId: string) { setDetail(await api<Detail>(`/${workspaceId}`)) }
  function open(workspaceId: string) {
    if (!window.dispatchEvent(new Event('interviewbuddy:before-navigate', { cancelable: true }))) return
    void action(async () => {
      await refresh(workspaceId); setRun(null); setInstructions(''); setRunKey(id())
      setDraft({ kind: 'cover_letter', content: '', request_id: id() }); setFinding({ draft_id: '', severity: 'warning', message: '', request_id: id() }); setReminder({ due_date: '', note: '', request_id: id() })
    })
  }
  return <div className="career-page">
    <section className="card career-panel"><h2>Your application workspaces</h2><p className="subtle">Jobs, draft versions, review notes, and reminders are saved in the local backend. Each workspace keeps the confirmed profile version it started with. These records are separate from the manual job tracker and browser backups.</p>
      <div className="actions">{items.map(item => <Button key={item.id} variant="secondary" disabled={busy} onClick={() => open(item.id)}>{item.company} · {item.role}{item.profile_revision ? ` · Profile v${item.profile_revision}` : ''}</Button>)}</div>{!items.length && <p>No workspaces yet. Add a job below to get started.</p>}
      {error && <div className="career-error" role="alert"><p>{error}</p><Button variant="secondary" disabled={busy} onClick={() => { setError(''); setReload(value => value + 1) }}>Reload workspace list</Button></div>}
      {notice && <p className="career-notice" role="status">{notice}</p>}
    </section>
    <details className="card career-panel" open={!detail}><summary>Create an application workspace</summary><form onSubmit={event => { event.preventDefault(); if (!window.dispatchEvent(new Event('interviewbuddy:before-workspace-change', { cancelable: true }))) return; if ((draft.content || finding.message || reminder.note || instructions) && !window.confirm('Discard unsaved entries in the current workspace?')) return; void action(async () => {
      const created = await api<Workspace>('', job); await refresh(created.id); setItems(await api<Workspace[]>('')); setRun(null); setInstructions(''); setRunKey(id()); setDraft({ kind: 'cover_letter', content: '', request_id: id() }); setFinding({ draft_id: '', severity: 'warning', message: '', request_id: id() }); setReminder({ due_date: '', note: '', request_id: id() })
      setJob({ resume_id: job.resume_id, company: '', role: '', description: '', url: '', request_id: id() }); setNotice('Workspace saved with a snapshot of your confirmed profile.')
    }) }}><fieldset disabled={busy} className="workspace-fields"><div className="field"><label htmlFor="workspace-resume">Confirmed resume profile</label><select id="workspace-resume" required value={job.resume_id} onChange={event => setJob({ ...job, resume_id: event.target.value, request_id: id() })}><option value="">Choose a resume</option>{resumes.map(resume => <option key={resume.id} value={resume.id}>{resume.filename}</option>)}</select><p className="field-hint">Confirm the profile in Career Profile before using it here.</p></div>
      {(['company', 'role', 'url', 'description'] as const).map(key => <div className="field" key={key}><label htmlFor={`job-${key}`}>{key === 'url' ? 'Application URL (optional)' : key === 'description' ? 'Job description' : key === 'company' ? 'Company' : 'Role'}</label>{key === 'description' ? <textarea id={`job-${key}`} rows={5} required value={job[key]} onChange={event => setJob({ ...job, [key]: event.target.value, request_id: id() })} /> : <input id={`job-${key}`} type={key === 'url' ? 'url' : 'text'} required={key !== 'url'} value={job[key]} onChange={event => setJob({ ...job, [key]: event.target.value, request_id: id() })} />}</div>)}<Button type="submit">Create workspace</Button></fieldset></form></details>
    {detail && <section className="card career-editor"><div className="career-section-heading"><div><h2>{detail.company} · {detail.role}</h2><p className="subtle">Profile version {detail.profile_snapshot.profile_revision} · preserved for every draft in this workspace</p></div></div>
      {detail.previous_workspace_id && <p className="subtle">Reassessed using an updated profile. <Button variant="secondary" onClick={() => open(detail.previous_workspace_id!)}>View previous drafts</Button></p>}
      {detail.url && <a href={detail.url} target="_blank" rel="noreferrer">Open application page</a>}<details className="career-details"><summary>Job description</summary><pre>{detail.description}</pre></details>
      <AgentFlowPanel key={detail.id} workspaceId={detail.id} runs={detail.runs} onSaved={() => refresh(detail.id)} />
      <h3>Saved drafts</h3>{!detail.drafts.length && <p className="subtle">No drafts yet. Prepare an application with the agents above, or save your own draft below.</p>}{detail.drafts.map(item => <details className="career-details" key={item.id}><summary>{item.kind.replaceAll('_', ' ')} · version {detail.drafts.filter(d => d.kind === item.kind).indexOf(item) + 1}</summary><pre>{item.content}</pre>{detail.findings.filter(f => f.draft_id === item.id).map(f => <p key={f.id}><strong>{f.severity}:</strong> {f.message}</p>)}</details>)}
      <form onSubmit={event => { event.preventDefault(); void action(async () => { await api(`/${detail.id}/drafts`, draft); await refresh(detail.id); setDraft({ ...draft, content: '', request_id: id() }); setNotice('New draft version saved.') }) }}><fieldset disabled={busy} className="workspace-fields"><div className="field"><label htmlFor="draft-kind">Draft type</label><select id="draft-kind" value={draft.kind} onChange={event => setDraft({ ...draft, kind: event.target.value, request_id: id() })}>{['cover_letter', 'resume_suggestions', 'screening_answers', 'other'].map(kind => <option key={kind} value={kind}>{kind.replaceAll('_', ' ')}</option>)}</select></div><div className="field"><label htmlFor="draft-content">New draft version</label><textarea id="draft-content" required rows={5} value={draft.content} onChange={event => setDraft({ ...draft, content: event.target.value, request_id: id() })} /></div><Button type="submit">Save draft version</Button></fieldset></form>
      {!!detail.drafts.length && <form onSubmit={event => { event.preventDefault(); void action(async () => { await api(`/${detail.id}/findings`, finding); await refresh(detail.id); setFinding({ ...finding, message: '', request_id: id() }); setNotice('Review note saved.') }) }}><fieldset disabled={busy} className="workspace-fields"><h3>Review findings</h3><div className="field"><label htmlFor="finding-draft">Draft to review</label><select id="finding-draft" required value={finding.draft_id} onChange={event => setFinding({ ...finding, draft_id: event.target.value, request_id: id() })}><option value="">Choose a draft</option>{detail.drafts.map((item, i) => <option key={item.id} value={item.id}>{item.kind.replaceAll('_', ' ')} · draft {i + 1}</option>)}</select></div><div className="field"><label htmlFor="finding-severity">Severity</label><select id="finding-severity" value={finding.severity} onChange={event => setFinding({ ...finding, severity: event.target.value, request_id: id() })}>{['info', 'warning', 'blocking'].map(value => <option key={value}>{value}</option>)}</select></div><div className="field"><label htmlFor="finding-message">Review note</label><textarea id="finding-message" required value={finding.message} onChange={event => setFinding({ ...finding, message: event.target.value, request_id: id() })} /></div><Button type="submit" variant="secondary">Save review note</Button></fieldset></form>}
      <h3>Review reminders</h3>{detail.reminders.map(item => <div className="workspace-reminder" key={item.id}><p>{item.due_date} · {item.note}{item.done ? ' · Done' : ''}</p>{!item.done && <Button disabled={busy} variant="secondary" onClick={() => void action(async () => { await api(`/${detail.id}/reminders/${item.id}/complete`, {}); await refresh(detail.id) })}>Mark done</Button>}</div>)}
      <form onSubmit={event => { event.preventDefault(); void action(async () => { await api(`/${detail.id}/reminders`, reminder); await refresh(detail.id); setReminder({ due_date: '', note: '', request_id: id() }); setNotice('Reminder saved. It appears in this workspace; email notifications are not enabled.') }) }}><fieldset disabled={busy} className="workspace-fields"><div className="field"><label htmlFor="reminder-date">Review date</label><input id="reminder-date" type="date" required value={reminder.due_date} onChange={event => setReminder({ ...reminder, due_date: event.target.value, request_id: id() })} /></div><div className="field"><label htmlFor="reminder-note">Reminder</label><input id="reminder-note" required value={reminder.note} onChange={event => setReminder({ ...reminder, note: event.target.value, request_id: id() })} /></div><Button type="submit" variant="secondary">Save reminder</Button></fieldset></form>
      <details className="career-details"><summary>Workflow setup & saved runs</summary><p>Prepare a persistent run, pause for instructions, and continue after reopening the app. This sets up the workspace for the upcoming agents; it does not generate applications yet.</p><div className="actions"><Button disabled={busy} variant="secondary" onClick={() => void action(async () => { const saved = await api<Run>(`/${detail.id}/runs`, { request_id: runKey }); setRun(saved); await refresh(detail.id); setRunKey(id()) })}>Prepare saved run</Button>{detail.runs.filter(item => item.workflow !== 'application_v1').map(item => <Button disabled={busy} key={item.id} variant="secondary" onClick={() => void action(async () => { setRun(await api<Run>(`/${detail.id}/runs/${item.id}`)) })}>Open run {item.id.slice(0, 8)}</Button>)}</div>
      {run && <><p>Status: {run.state.phase?.replaceAll('_', ' ')}</p>{run.paused ? <form onSubmit={event => { event.preventDefault(); void action(async () => { setRun(await api<Run>(`/${detail.id}/runs/${run.id}/resume`, { checkpoint_id: run.checkpoint_id, instructions })); setInstructions(''); setNotice('Run resumed and instructions saved.') }) }}><div className="field"><label htmlFor="run-instructions">Application instructions</label><textarea id="run-instructions" required maxLength={5000} disabled={busy} value={instructions} onChange={event => setInstructions(event.target.value)} /></div><Button disabled={busy} type="submit">Save instructions and continue</Button></form> : <p>{run.state.instructions}</p>}</>}
      </details>
    </section>}
  </div>
}
