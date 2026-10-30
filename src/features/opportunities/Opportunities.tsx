import { useEffect, useState } from 'react'
import { Search, Bell, ExternalLink } from 'lucide-react'
import { Button } from '../../components/Button'
import { useToday } from '../../utils/useToday'
import '../career-profile/career-profile.css'

type Job = { candidate_id: string; company: string; role: string; source: string; location: string; url: string }
type Match = { candidate_id: string; eligible: boolean; score: number; reason: string; cautions: string[] }
type Batch = { id: string; status: string; is_running?: boolean; created_at: string; progress: { error?: string; source_errors?: string[]; events: string[]; candidates?: Job[]; matches?: Match[]; items: { candidate_id: string; workspace_id?: string; status: string; error?: string; outcome_reason?: string; match: Match }[] } }
type Reminder = { id: string; workspace_id: string; due_date: string; company: string; role: string; note: string }
type Resume = { id: string; filename: string }
async function get<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(body) })
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as { detail?: unknown }
    throw new Error(response.status === 404 ? 'Opportunity discovery is unavailable. Restart the backend and reload.' : typeof error.detail === 'string' ? error.detail : 'Could not load opportunities. Check the backend connection.')
  }
  return response.json() as Promise<T>
}

export function Opportunities({ onOpenWorkspace }: { onOpenWorkspace: (workspaceId: string) => void }) {
  const today = useToday()
  const [batches, setBatches] = useState<Batch[]>([])
  const [resumes, setResumes] = useState<Resume[]>([])
  const [queue, setQueue] = useState<Reminder[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [reload, setReload] = useState(0)
  const [form, setForm] = useState(() => ({ resume_id: '', max_applications: 3, review_date: today, request_id: crypto.randomUUID() }))
  useEffect(() => {
    let active = true
    let fetching = false
    async function load() {
      if (fetching) return
      fetching = true
      try {
        const [saved, files, reminders] = await Promise.all([get<Batch[]>('/api/discovery'), get<Resume[]>('/api/resumes'), get<Reminder[]>('/api/discovery/review-queue')])
        if (active) { setBatches(saved); setResumes(files); setQueue(reminders); setError('') }
      } catch (failure) { if (active) setError(failure instanceof Error ? failure.message : 'Could not load saved opportunities.') }
      finally { fetching = false }
    }
    void load()
    const timer = window.setInterval(() => void load(), 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [reload])
  async function start() {
    setBusy(true); setError(''); setNotice('')
    try {
      const batch = await get<Batch>('/api/discovery', form)
      setBatches(items => [batch, ...items.filter(item => item.id !== batch.id)])
      setForm({ ...form, request_id: crypto.randomUUID() })
      setNotice('Search started. The agents will prepare drafts and reminders without asking intermediate questions. You can leave this screen while the backend is running.')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not start discovery.') }
    finally { setBusy(false) }
  }
  const active = batches.some(batch => ['queued', 'running'].includes(batch.status))
  return <div className="career-page">
    <section className="card career-panel"><div className="career-section-heading"><div><p className="eyebrow">JOB DISCOVERY</p><h2>Find opportunities. Review when ready.</h2></div><Search aria-hidden="true" /></div>
      <p>The agents find relevant roles, filter against your confirmed profile and preferences, prepare drafts, and add review reminders. Unknown details are flagged for your final review.</p>
      <p className="subtle">Coverage: <a href="https://remotive.com" target="_blank" rel="noreferrer">Remotive</a> remote roles and <a href="https://www.arbeitnow.com" target="_blank" rel="noreferrer">Arbeitnow</a> mainly European jobs. Location restrictions still apply to remote roles. Listings can be delayed or closed by the time you review them.</p>
      <form onSubmit={event => { event.preventDefault(); void start() }}><fieldset disabled={busy || active} className="workspace-fields"><div className="career-preference-grid"><div className="field"><label htmlFor="discovery-profile">Resume profile</label><select id="discovery-profile" required value={form.resume_id} onChange={event => setForm({ ...form, resume_id: event.target.value, request_id: crypto.randomUUID() })}><option value="">Choose a confirmed profile</option>{resumes.map(resume => <option value={resume.id} key={resume.id}>{resume.filename}</option>)}</select><p className="field-hint">Set target roles, locations, and exclusions in Career Profile, then confirm it.</p></div><div className="field"><label htmlFor="discovery-limit">Maximum applications per run</label><select id="discovery-limit" value={form.max_applications} onChange={event => setForm({ ...form, max_applications: Number(event.target.value), request_id: crypto.randomUUID() })}>{[1, 2, 3].map(value => <option key={value} value={value}>{value}</option>)}</select></div><div className="field"><label htmlFor="discovery-date">Remind me to review on</label><input id="discovery-date" type="date" required value={form.review_date} onChange={event => setForm({ ...form, review_date: event.target.value, request_id: crypto.randomUUID() })} /></div></div>
      <p className="subtle">Starting sends profile facts and preferences to Groq for matching and drafting. Public job feeds receive no resume information. The backend must stay running; scheduled execution and email are not enabled yet.</p><Button type="submit"><Search size={17} />{busy ? 'Starting…' : active ? 'Discovery in progress…' : 'Find opportunities'}</Button></fieldset></form>
      {notice && <p role="status" className="career-notice">{notice}</p>}{error && <div role="alert" className="career-error"><p>{error}</p><Button variant="secondary" onClick={() => setReload(value => value + 1)}>Reload opportunities</Button></div>}
    </section>
    <section className="card career-panel"><div className="career-section-heading"><h2><Bell size={20} aria-hidden="true" /> Your review reminders</h2><span className="career-badge">{queue.length} pending</span></div>{queue.length ? queue.map(item => <div className="workspace-reminder" key={item.id}><div><strong>{item.company} · {item.role}</strong><p>{item.due_date}{item.due_date < today ? ' · Overdue' : item.due_date === today ? ' · Today' : ''} · {item.note}</p></div><Button variant="secondary" onClick={() => { if (item.workspace_id) onOpenWorkspace(item.workspace_id) }}>Review drafts</Button></div>) : <p>Your prepared applications and review reminders will appear here.</p>}</section>
    <section className="card career-panel"><h2>Discovery history</h2>{!batches.length && <p>No discovery runs yet.</p>}{batches.map(batch => <div className="agent-results" key={batch.id}><div className="career-section-heading"><h3>{new Date(batch.created_at).toLocaleString()}</h3><span className="career-badge">{batch.status}</span></div>
      {!['queued', 'running'].includes(batch.status) && batch.progress.error && <p className="field-error">{batch.progress.error}</p>}{batch.progress.source_errors?.map((message, i) => <p key={i}>{message}</p>)}
      {['queued', 'running'].includes(batch.status) && <p role="status">Agents are working independently. If the backend was restarted, resume this saved run.</p>}
      {batch.progress.items.map(item => { const job = batch.progress.candidates?.find(candidate => candidate.candidate_id === item.candidate_id); return <div className="agent-requirement" key={item.candidate_id}><strong>{job?.company} · {job?.role}</strong><p>{item.status.replaceAll('_', ' ')} · Match score {item.match.score}/100</p><p>{item.match.reason}</p>{item.outcome_reason && <p>{item.outcome_reason}</p>}{item.match.cautions.map((caution, i) => <p key={i}>Check before submitting: {caution}</p>)}{item.error && <p className="field-error">{item.error}</p>}{job && <p>Source: <a href={job.url} target="_blank" rel="noreferrer">{job.source} <ExternalLink size={13} aria-hidden="true" /></a> · {job.location}</p>}{item.workspace_id && <Button variant="secondary" onClick={() => { if (item.workspace_id) onOpenWorkspace(item.workspace_id) }}>Open application workspace</Button>}</div> })}
      {!batch.progress.items.length && batch.status === 'completed' && <p>No new suitable roles were found in this batch. Review your preferences or try again when the feeds refresh.</p>}
      <details className="career-details"><summary>Matching decisions and activity</summary>{batch.progress.matches?.filter(match => !match.eligible || match.score < 65).map(match => <p key={match.candidate_id}>Skipped {batch.progress.candidates?.find(candidate => candidate.candidate_id === match.candidate_id)?.role}: {match.reason}</p>)}<ol>{batch.progress.events.map((message, i) => <li key={i}>{message}</li>)}</ol></details>
      {(['queued', 'running', 'failed'].includes(batch.status) || batch.progress.items.some(item => item.status === 'deferred')) && <Button variant="secondary" disabled={busy || batch.is_running} onClick={async () => { setBusy(true); try { const updated = await get<Batch>(`/api/discovery/${batch.id}/retry`, {}); setBatches(items => items.map(item => item.id === batch.id ? updated : item)); setReload(value => value + 1) } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not resume saved batch.') } finally { setBusy(false) } }}>{batch.is_running ? 'Batch is running…' : 'Resume saved batch'}</Button>}
    </div>)}</section>
  </div>
}
