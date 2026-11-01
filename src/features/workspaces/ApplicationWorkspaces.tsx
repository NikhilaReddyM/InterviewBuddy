import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { BriefcaseBusiness, Search, Plus, ArrowUpRight, FileText, ClipboardCheck, Globe, Sparkles, History, Bell, RefreshCw, ChevronRight } from 'lucide-react'
import { ReviewPanel } from './ReviewPanel'
import { ApplicationFormPanel } from './ApplicationFormPanel'
import './workspaces.css'
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
const tabs = [
  { id: 'review', label: 'Review', icon: ClipboardCheck },
  { id: 'form', label: 'Employer form', icon: Globe },
  { id: 'agents', label: 'Agent runs', icon: Sparkles },
  { id: 'history', label: 'Draft history', icon: History },
  { id: 'notes', label: 'Notes & reminders', icon: Bell },
] as const
type WorkspaceTab = typeof tabs[number]['id']

export function ApplicationWorkspaces({ initialWorkspaceId }: { initialWorkspaceId?: string } = {}) {
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [profileFilter, setProfileFilter] = useState('all')
  const [visibleItems, setVisibleItems] = useState(6)
  const [creating, setCreating] = useState(false)
  const [tab, setTab] = useState<WorkspaceTab>('review')
  const detailHeading = useRef<HTMLHeadingElement>(null)
  const createSection = useRef<HTMLDetailsElement>(null)
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
    }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : 'Could not load workspaces.') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reload])
  useEffect(() => {
    if (!initialWorkspaceId) return
    let active = true
    api<Detail>(`/${initialWorkspaceId}`).then(value => { if (active) { setDetail(value); setTab('review') } }).catch(failure => { if (active) setError(failure instanceof Error ? failure.message : 'Could not open workspace.') })
    return () => { active = false }
  }, [initialWorkspaceId])
  useEffect(() => {
    if (detail?.id) requestAnimationFrame(() => { detailHeading.current?.scrollIntoView?.({ block: 'start' }); detailHeading.current?.focus({ preventScroll: true }) })
  }, [detail?.id])
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
  function open(workspaceId: string, nextTab: WorkspaceTab = 'review') {
    if (!window.dispatchEvent(new Event('interviewbuddy:before-navigate', { cancelable: true }))) return
    void action(async () => {
      await refresh(workspaceId); setTab(nextTab); setCreating(false); setJob({ resume_id: job.resume_id, company: '', role: '', description: '', url: '', request_id: id() }); setRun(null); setInstructions(''); setRunKey(id())
      setDraft({ kind: 'cover_letter', content: '', request_id: id() }); setFinding({ draft_id: '', severity: 'warning', message: '', request_id: id() }); setReminder({ due_date: '', note: '', request_id: id() })
    })
  }
  const versions = [...new Set(items.map(item => item.profile_revision).filter((value): value is number => value !== undefined))].sort((a, b) => b - a)
  const filtered = items.filter(item => `${item.company} ${item.role}`.toLowerCase().includes(search.trim().toLowerCase()) && (profileFilter === 'all' || String(item.profile_revision) === profileFilter))
  function beginCreate() {
    setCreating(true)
    requestAnimationFrame(() => { createSection.current?.scrollIntoView?.({ block: 'start' }); document.getElementById('workspace-resume')?.focus() })
  }
  function moveTab(event: KeyboardEvent, index: number) {
    let next = index
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
    else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = tabs.length - 1
    else return
    event.preventDefault(); setTab(tabs[next].id); document.getElementById(`workspace-tab-${tabs[next].id}`)?.focus()
  }
  return <div className="career-page workspace-page">
    <section className="card career-panel workspace-library" aria-labelledby="workspace-library-title">
      <div className="workspace-library-header"><div className="discovery-heading"><span className="discovery-icon"><BriefcaseBusiness size={22} aria-hidden="true" /></span><div><p className="eyebrow">YOUR APPLICATIONS</p><h2 id="workspace-library-title">Application library</h2></div></div><Button disabled={busy} onClick={beginCreate}><Plus size={17} />Add a job</Button></div>
      <p className="workspace-intro">Keep each role’s drafts, employer form, and review notes together. Choose an application to continue.</p>
      <div className="workspace-library-controls"><div className="field"><label htmlFor="workspace-search">Find company or role</label><div className="workspace-search-control"><Search size={18} aria-hidden="true" /><input id="workspace-search" type="search" placeholder="Search your applications…" value={search} onChange={event => { setSearch(event.target.value); setVisibleItems(6) }} /></div></div><div className="field"><label htmlFor="workspace-profile-filter">Profile version</label><select id="workspace-profile-filter" value={profileFilter} onChange={event => { setProfileFilter(event.target.value); setVisibleItems(6) }}><option value="all">All versions</option>{versions.map(version => <option value={version} key={version}>Version {version}</option>)}</select></div></div>
      {loading ? <p role="status" className="subtle">Loading your applications…</p> : <><p className="workspace-list-count">{filtered.length} of {items.length} saved {items.length === 1 ? 'workspace' : 'workspaces'}</p><div className="workspace-card-grid">{filtered.slice(0, visibleItems).map(item => <button type="button" key={item.id} className={`workspace-choice${detail?.id === item.id ? ' workspace-choice--selected' : ''}`} aria-pressed={detail?.id === item.id} aria-label={`${item.company} · ${item.role}${item.profile_revision ? ` · Profile v${item.profile_revision}` : ''}`} disabled={busy} onClick={() => open(item.id)}><div className="workspace-choice-top"><span className="workspace-company-mark" aria-hidden="true">{item.company.trim().slice(0, 2).toUpperCase()}</span><span>{detail?.id === item.id ? 'Selected' : 'Open workspace'}<ChevronRight size={14} aria-hidden="true" /></span></div><strong>{item.company}</strong><span className="workspace-choice-role">{item.role}</span><span className="workspace-choice-profile"><FileText size={13} aria-hidden="true" />{item.profile_revision ? `Profile version ${item.profile_revision}` : 'Saved profile snapshot'}</span></button>)}</div>
      {!items.length && !error && <div className="workspace-empty"><BriefcaseBusiness size={30} aria-hidden="true" /><h3>Your next application starts here</h3><p>Discovery jobs appear here automatically. You can also add a job description yourself.</p><Button variant="secondary" onClick={beginCreate}>Create your first workspace</Button></div>}
      {!!items.length && !filtered.length && <div className="workspace-empty"><p>No applications match these filters.</p><Button variant="secondary" onClick={() => { setSearch(''); setProfileFilter('all'); setVisibleItems(6) }}>Clear filters</Button></div>}
      {filtered.length > visibleItems && <Button variant="secondary" className="workspace-show-more" onClick={() => setVisibleItems(value => value + 6)}>Show more workspaces ({filtered.length - visibleItems} more)</Button>}</>}
      {error && <div className="career-error" role="alert"><p>{error}</p><Button variant="secondary" disabled={busy} onClick={() => { setError(''); setLoading(true); setReload(value => value + 1) }}>Reload workspace list</Button></div>}
      {notice && <p className="career-notice" role="status">{notice}</p>}
    </section>
    <details ref={createSection} className="card career-panel workspace-create" open={creating} onToggle={event => setCreating(event.currentTarget.open)}><summary><Plus size={18} aria-hidden="true" />Create an application workspace<span>For a job description you already have</span></summary><form onSubmit={event => { event.preventDefault(); if (!window.dispatchEvent(new Event('interviewbuddy:before-workspace-change', { cancelable: true }))) return; if ((draft.content || finding.message || reminder.note || instructions) && !window.confirm('Discard unsaved entries in the current workspace?')) return; void action(async () => {
      const created = await api<Workspace>('', job); await refresh(created.id); setTab('review'); setCreating(false); setItems(await api<Workspace[]>('')); setRun(null); setInstructions(''); setRunKey(id()); setDraft({ kind: 'cover_letter', content: '', request_id: id() }); setFinding({ draft_id: '', severity: 'warning', message: '', request_id: id() }); setReminder({ due_date: '', note: '', request_id: id() })
      setJob({ resume_id: job.resume_id, company: '', role: '', description: '', url: '', request_id: id() }); setNotice('Workspace saved with a snapshot of your confirmed profile.')
    }) }}><fieldset disabled={busy} className="workspace-fields"><div className="field"><label htmlFor="workspace-resume">Confirmed resume profile</label><select id="workspace-resume" required value={job.resume_id} onChange={event => setJob({ ...job, resume_id: event.target.value, request_id: id() })}><option value="">Choose a resume</option>{resumes.map(resume => <option key={resume.id} value={resume.id}>{resume.filename}</option>)}</select><p className="field-hint">Confirm the profile in Career Profile before using it here.</p></div>
      {(['company', 'role', 'url', 'description'] as const).map(key => <div className="field" key={key}><label htmlFor={`job-${key}`}>{key === 'url' ? 'Application URL (optional)' : key === 'description' ? 'Job description' : key === 'company' ? 'Company' : 'Role'}</label>{key === 'description' ? <textarea id={`job-${key}`} rows={5} required value={job[key]} onChange={event => setJob({ ...job, [key]: event.target.value, request_id: id() })} /> : <input id={`job-${key}`} type={key === 'url' ? 'url' : 'text'} required={key !== 'url'} value={job[key]} onChange={event => setJob({ ...job, [key]: event.target.value, request_id: id() })} />}</div>)}<Button type="submit">Create workspace</Button></fieldset></form></details>

    {detail ? <section className="card career-editor workspace-detail" aria-labelledby="workspace-detail-title">
      <header className="workspace-detail-header"><div><p className="eyebrow">SELECTED APPLICATION</p><h2 ref={detailHeading} tabIndex={-1} id="workspace-detail-title">{detail.company} · {detail.role}</h2><p className="workspace-profile-note">Profile version {detail.profile_snapshot.profile_revision} · kept with every draft in this workspace</p></div><div className="actions">{detail.url && <a className="button button--secondary" href={detail.url} target="_blank" rel="noreferrer">View job posting<ArrowUpRight size={16} aria-hidden="true" /></a>}<Button variant="secondary" disabled={busy} onClick={() => void action(() => refresh(detail.id))}><RefreshCw size={16} />Refresh workspace</Button></div></header>
      <div className="workspace-metrics"><div><FileText size={17} aria-hidden="true" /><span><strong>{detail.drafts.length}</strong> saved draft versions</span></div><div><ClipboardCheck size={17} aria-hidden="true" /><span><strong>{detail.findings.length}</strong> review notes</span></div><div><Bell size={17} aria-hidden="true" /><span><strong>{detail.reminders.filter(item => !item.done).length}</strong> pending reminders</span></div></div>
      {detail.previous_workspace_id && <p className="workspace-reassessment">Reassessed using an updated profile. <Button variant="secondary" disabled={busy} onClick={() => open(detail.previous_workspace_id!, 'history')}>View previous drafts</Button></p>}
      <details className="career-details workspace-job-description"><summary>Job description</summary><pre>{detail.description}</pre></details>
      <div className="workspace-tabs" role="tablist" aria-label="Workspace sections">{tabs.map((item, index) => <button key={item.id} id={`workspace-tab-${item.id}`} role="tab" type="button" aria-selected={tab === item.id} aria-controls={`workspace-panel-${item.id}`} tabIndex={tab === item.id ? 0 : -1} onKeyDown={event => moveTab(event, index)} onClick={() => setTab(item.id)}><item.icon size={16} aria-hidden="true" />{item.label}</button>)}</div>
      <div id="workspace-panel-review" role="tabpanel" aria-labelledby="workspace-tab-review" hidden={tab !== 'review'} className="workspace-tab-panel"><ReviewPanel key={`review-${detail.id}`} workspaceId={detail.id} initiallyOpen={detail.id === initialWorkspaceId} onSaved={() => refresh(detail.id)} /></div>
      <div id="workspace-panel-form" role="tabpanel" aria-labelledby="workspace-tab-form" hidden={tab !== 'form'} className="workspace-tab-panel"><ApplicationFormPanel key={`form-${detail.id}`} workspaceId={detail.id} /></div>
      <div id="workspace-panel-agents" role="tabpanel" aria-labelledby="workspace-tab-agents" hidden={tab !== 'agents'} className="workspace-tab-panel"><AgentFlowPanel key={detail.id} workspaceId={detail.id} runs={detail.runs} onSaved={() => refresh(detail.id)} />
      <details className="career-details"><summary>Advanced: legacy setup runs</summary><p>Legacy setup runs save instructions only. Use Application Copilot above to generate or resume application drafts.</p><div className="actions"><Button disabled={busy} variant="secondary" onClick={() => void action(async () => { const saved = await api<Run>(`/${detail.id}/runs`, { request_id: runKey }); setRun(saved); await refresh(detail.id); setRunKey(id()) })}>Prepare saved run</Button>{detail.runs.filter(item => item.workflow !== 'application_v1').map(item => <Button disabled={busy} key={item.id} variant="secondary" onClick={() => void action(async () => { setRun(await api<Run>(`/${detail.id}/runs/${item.id}`)) })}>Open run {item.id.slice(0, 8)}</Button>)}</div>
      {run && <><p>Status: {run.state.phase?.replaceAll('_', ' ')}</p>{run.paused ? <form onSubmit={event => { event.preventDefault(); void action(async () => { setRun(await api<Run>(`/${detail.id}/runs/${run.id}/resume`, { checkpoint_id: run.checkpoint_id, instructions })); setInstructions(''); setNotice('Run resumed and instructions saved.') }) }}><div className="field"><label htmlFor="run-instructions">Application instructions</label><textarea id="run-instructions" required maxLength={5000} disabled={busy} value={instructions} onChange={event => setInstructions(event.target.value)} /></div><Button disabled={busy} type="submit">Save instructions and continue</Button></form> : <p>{run.state.instructions}</p>}</>}
      </details>
      </div>
      <div id="workspace-panel-history" role="tabpanel" aria-labelledby="workspace-tab-history" hidden={tab !== 'history'} className="workspace-tab-panel"><div className="workspace-panel-heading"><h3>Draft history</h3><p>Earlier versions stay available. Save a new version below to add your own text.</p></div>
      <h3>All saved versions</h3>{!detail.drafts.length && <p className="subtle">No drafts yet. Prepare an application with the agents above, or save your own draft below.</p>}{detail.drafts.map(item => <details className="career-details" key={item.id}><summary>{item.kind.replaceAll('_', ' ')} · version {detail.drafts.filter(d => d.kind === item.kind).indexOf(item) + 1}</summary><pre>{item.content}</pre>{detail.findings.filter(f => f.draft_id === item.id).map(f => <p key={f.id}><strong>{f.severity}:</strong> {f.message}</p>)}</details>)}
      <form onSubmit={event => { event.preventDefault(); void action(async () => { await api(`/${detail.id}/drafts`, draft); await refresh(detail.id); setDraft({ ...draft, content: '', request_id: id() }); setNotice('New draft version saved.') }) }}><fieldset disabled={busy} className="workspace-fields"><div className="field"><label htmlFor="draft-kind">Draft type</label><select id="draft-kind" value={draft.kind} onChange={event => setDraft({ ...draft, kind: event.target.value, request_id: id() })}>{['cover_letter', 'resume_suggestions', 'screening_answers', 'other'].map(kind => <option key={kind} value={kind}>{kind.replaceAll('_', ' ')}</option>)}</select></div><div className="field"><label htmlFor="draft-content">New draft version</label><textarea id="draft-content" required rows={5} value={draft.content} onChange={event => setDraft({ ...draft, content: event.target.value, request_id: id() })} /></div><Button type="submit">Save draft version</Button></fieldset></form>
      </div>
      <div id="workspace-panel-notes" role="tabpanel" aria-labelledby="workspace-tab-notes" hidden={tab !== 'notes'} className="workspace-tab-panel"><div className="workspace-panel-heading"><h3>Notes & reminders</h3><p>Keep your review notes and follow-up dates with this application.</p></div>
      {!!detail.drafts.length && <form onSubmit={event => { event.preventDefault(); void action(async () => { await api(`/${detail.id}/findings`, finding); await refresh(detail.id); setFinding({ ...finding, message: '', request_id: id() }); setNotice('Review note saved.') }) }}><fieldset disabled={busy} className="workspace-fields"><h3>Review findings</h3><div className="field"><label htmlFor="finding-draft">Draft to review</label><select id="finding-draft" required value={finding.draft_id} onChange={event => setFinding({ ...finding, draft_id: event.target.value, request_id: id() })}><option value="">Choose a draft</option>{detail.drafts.map((item, i) => <option key={item.id} value={item.id}>{item.kind.replaceAll('_', ' ')} · draft {i + 1}</option>)}</select></div><div className="field"><label htmlFor="finding-severity">Severity</label><select id="finding-severity" value={finding.severity} onChange={event => setFinding({ ...finding, severity: event.target.value, request_id: id() })}>{['info', 'warning', 'blocking'].map(value => <option key={value}>{value}</option>)}</select></div><div className="field"><label htmlFor="finding-message">Review note</label><textarea id="finding-message" required value={finding.message} onChange={event => setFinding({ ...finding, message: event.target.value, request_id: id() })} /></div><Button type="submit" variant="secondary">Save review note</Button></fieldset></form>}
      <h3>Review reminders</h3>{detail.reminders.map(item => <div className="workspace-reminder" key={item.id}><p>{item.due_date} · {item.note}{item.done ? ' · Done' : ''}</p>{!item.done && <Button disabled={busy} variant="secondary" onClick={() => void action(async () => { await api(`/${detail.id}/reminders/${item.id}/complete`, {}); await refresh(detail.id) })}>Mark done</Button>}</div>)}
      <form onSubmit={event => { event.preventDefault(); void action(async () => { await api(`/${detail.id}/reminders`, reminder); await refresh(detail.id); setReminder({ due_date: '', note: '', request_id: id() }); setNotice('Reminder saved. Your configured review queue and email settings apply.') }) }}><fieldset disabled={busy} className="workspace-fields"><div className="field"><label htmlFor="reminder-date">Review date</label><input id="reminder-date" type="date" required value={reminder.due_date} onChange={event => setReminder({ ...reminder, due_date: event.target.value, request_id: id() })} /></div><div className="field"><label htmlFor="reminder-note">Reminder</label><input id="reminder-note" required value={reminder.note} onChange={event => setReminder({ ...reminder, note: event.target.value, request_id: id() })} /></div><Button type="submit" variant="secondary">Save reminder</Button></fieldset></form>
      </div>
      <p className="workspace-storage-note">Saved in your local backend with a fixed profile snapshot. Final application submission stays with you.</p>
    </section> : !loading && !!items.length && <div className="workspace-selection-hint"><ClipboardCheck size={23} aria-hidden="true" /><div><strong>Pick an application to continue</strong><p>Review drafts, restore an employer form, or resume an agent run from its workspace.</p></div></div>}
  </div>
}
