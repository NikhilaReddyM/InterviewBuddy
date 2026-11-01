import { useEffect, useRef, useState } from 'react'
import { Search, Bell, ExternalLink, FileText, CheckCircle2, ArrowRight, CalendarDays, Loader2 } from 'lucide-react'
import { EmailDigest } from './EmailDigest'
import { ApplicationFormSettings } from './ApplicationFormSettings'
import { DiscoverySchedules } from './DiscoverySchedules'
import { JobCatalog } from './JobCatalog'
import { ReviewPreferences } from './ReviewPreferences'
import { CooldownStatus } from './CooldownStatus'
import { Button } from '../../components/Button'
import { useToday } from '../../utils/useToday'
import '../career-profile/career-profile.css'

type Job = { candidate_id: string; company: string; role: string; source: string; location: string; url: string }
type Match = { candidate_id: string; eligible: boolean; score: number; reason: string; cautions: string[] }
type Batch = { id: string; status: string; is_running?: boolean; can_redraft_rejected?: boolean; cooldown_until?: number | null; server_time?: number; profile_revision?: number; profile_preferences?: { target_roles?: string; locations?: string; remote?: string; exclusions?: string }; created_at: string; progress: { error?: string; retry_at?: number; source_errors?: string[]; events: string[]; candidates?: Job[]; reassesses_batch_id?: string; match_results?: Match[]; matches?: Match[]; items: { candidate_id: string; workspace_id?: string; status: string; error?: string; outcome_reason?: string; match: Match }[] } }
type Reminder = { form_status?: string; profile_revision?: number; draft_count?: number; match?: Match | null; url?: string; id: string; workspace_id: string; due_date: string; company: string; role: string; note: string }
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
  const [clockOffset, setClockOffset] = useState(0)
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000); return () => window.clearInterval(timer) }, [])
  const reassessKeys = useRef<Record<string, string>>({})
  const [batches, setBatches] = useState<Batch[]>([])
  const [resumes, setResumes] = useState<Resume[]>([])
  const [queue, setQueue] = useState<Reminder[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [reload, setReload] = useState(0)
  const [runFilter, setRunFilter] = useState('all')
  const [runSearch, setRunSearch] = useState('')
  const [visibleRuns, setVisibleRuns] = useState(5)
  const [showAllReviews, setShowAllReviews] = useState(false)
  const [useReminderPreferences, setUseReminderPreferences] = useState(true)
  const [form, setForm] = useState(() => ({ resume_id: '', max_applications: 3, review_date: today, request_id: crypto.randomUUID() }))
  useEffect(() => {
    let active = true
    let fetching = false
    async function load() {
      if (fetching) return
      fetching = true
      try {
        const [saved, files, reminders] = await Promise.all([get<Batch[]>('/api/discovery'), get<Resume[]>('/api/resumes'), get<Reminder[]>('/api/discovery/review-queue')])
        if (active) { if (saved[0]?.server_time) setClockOffset(saved[0].server_time - Date.now() / 1000); setBatches(saved); setResumes(files); setQueue(reminders); setError('') }
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
      const batch = await get<Batch>('/api/discovery', { ...form, review_date: useReminderPreferences ? null : form.review_date })
      setBatches(items => [batch, ...items.filter(item => item.id !== batch.id)])
      setForm({ ...form, request_id: crypto.randomUUID() })
      setNotice('Search started. The agents will prepare drafts and reminders without asking intermediate questions. You can leave this screen while the backend is running.')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not start discovery.') }
    finally { setBusy(false) }
  }
  const active = batches.some(batch => ['queued', 'running'].includes(batch.status))
  const filteredRuns = batches.filter(batch => (runFilter === 'all' || (runFilter === 'active' ? ['queued', 'running'].includes(batch.status) : runFilter === 'attention' ? ['failed', 'waiting', 'partial'].includes(batch.status) || batch.can_redraft_rejected : batch.status === 'completed')) && (!runSearch.trim() || batch.progress.candidates?.some(job => `${job.company} ${job.role}`.toLowerCase().includes(runSearch.toLowerCase()))))
  return <div className="career-page opportunities-page">
    <nav className="opportunity-navigation" aria-label="Opportunity sections"><a href="#discovery-start">Discover</a><a href="#opportunity-reviews">Review queue <span>{queue.length}</span></a><a href="#discovery-history">Run history <span>{batches.length}</span></a><a href="#opportunity-settings" onClick={() => { const panel = document.getElementById('opportunity-settings'); if (panel instanceof HTMLDetailsElement) panel.open = true }}>Settings</a></nav>
    <section id="discovery-start" className="card career-panel job-discovery" aria-labelledby="discovery-title">
      <header className="discovery-header"><div className="discovery-heading"><span className="discovery-icon"><Search size={23} aria-hidden="true" /></span><div><p className="eyebrow">JOB DISCOVERY</p><h2 id="discovery-title">Start a job search</h2></div></div><span className="discovery-threshold">70+ match score</span></header>
      <p className="discovery-intro">Choose your profile. We’ll find relevant roles and prepare applications for your review.</p>
      <div className="discovery-layout">
        <form aria-label="Start job discovery" onSubmit={event => { event.preventDefault(); void start() }}>
          <fieldset disabled={busy || active} className="workspace-fields discovery-controls">
            <div className="discovery-inputs">
              <div className="field"><label htmlFor="discovery-profile">Resume profile</label><select id="discovery-profile" required aria-describedby="discovery-profile-hint" value={form.resume_id} onChange={event => setForm({ ...form, resume_id: event.target.value, request_id: crypto.randomUUID() })}><option value="">Choose a confirmed profile</option>{resumes.map(resume => <option value={resume.id} key={resume.id}>{resume.filename}</option>)}</select></div>
              <div className="field"><label htmlFor="discovery-limit">Maximum applications per run</label><select id="discovery-limit" aria-describedby="discovery-limit-hint" value={form.max_applications} onChange={event => setForm({ ...form, max_applications: Number(event.target.value), request_id: crypto.randomUUID() })}>{[1, 2, 3].map(value => <option key={value} value={value}>{value} {value === 1 ? 'application' : 'applications'}</option>)}</select></div>
            </div>
            <p id="discovery-profile-hint" className="discovery-helper">Use Career Profile to confirm your resume and update target roles, locations, and exclusions.</p>
            <div className="discovery-reminder"><div className="discovery-reminder-heading"><CalendarDays size={18} aria-hidden="true" /><strong>Review reminder</strong></div>
              <label className="discovery-reminder-choice"><input type="checkbox" checked={useReminderPreferences} onChange={event => { setUseReminderPreferences(event.target.checked); setForm({ ...form, request_id: crypto.randomUUID() }) }} />Use configured reminder timing instead of a specific date</label>
              {useReminderPreferences && <p className="discovery-helper">Your saved reminder preferences will be used when drafts are ready.</p>}
              <div className="field discovery-date" hidden={useReminderPreferences}><label htmlFor="discovery-date">Remind me to review on</label><input id="discovery-date" type="date" disabled={useReminderPreferences} required={!useReminderPreferences} value={form.review_date} onChange={event => setForm({ ...form, review_date: event.target.value, request_id: crypto.randomUUID() })} /></div>
            </div>
            <div className="discovery-launch"><Button type="submit" disabled={!form.resume_id}>{busy || active ? <Loader2 size={18} className="discovery-spinner" aria-hidden="true" /> : <Search size={18} aria-hidden="true" />}{busy ? 'Starting…' : active ? 'Discovery in progress…' : 'Find opportunities'}{!busy && !active && <ArrowRight size={17} aria-hidden="true" />}</Button><p id="discovery-limit-hint">{active ? 'A run is already in progress. Follow it in Run history.' : !form.resume_id ? 'Select a confirmed profile to start.' : `Prepare up to ${form.max_applications} ${form.max_applications === 1 ? 'application' : 'applications'} in this run.`}</p></div>
          </fieldset>
        </form>
        <aside className="discovery-process" aria-label="What happens next"><p className="eyebrow">WHAT HAPPENS NEXT</p><ol>
          <li><span className="discovery-step-icon"><Search size={17} aria-hidden="true" /></span><div><strong>Find your matches</strong><p>Roles scoring 70/100 or higher qualify for drafting.</p></div></li>
          <li><span className="discovery-step-icon"><FileText size={17} aria-hidden="true" /></span><div><strong>Prepare and check</strong><p>Agents draft materials and flag missing information.</p></div></li>
          <li><span className="discovery-step-icon"><CheckCircle2 size={17} aria-hidden="true" /></span><div><strong>Review when ready</strong><p>Open saved applications, check the details, and submit yourself.</p></div></li>
        </ol><p className="discovery-process-note">The agents work independently. Keep the backend running while they prepare your applications.</p></aside>
      </div>
      <details className="career-details discovery-coverage"><summary>Job coverage and how this run works</summary><p>Discovery reads selected Greenhouse and Ashby employer boards, <a href="https://remotive.com" target="_blank" rel="noreferrer">Remotive</a>, and <a href="https://www.arbeitnow.com" target="_blank" rel="noreferrer">Arbeitnow</a>. Coverage is selective, and listings may close before you review them. Remote roles can have location restrictions.</p><p>Your profile facts and preferences are processed by your configured model provider. Public job feeds receive no resume information. Enabled employer-form preparation can fill supported sites and upload your resume; final submission stays with you.</p><p>This button starts one discovery run. Recurring searches and email digests follow the schedules and settings you explicitly enable below.</p></details>
      {notice && <p role="status" className="career-notice">{notice}</p>}{error && <div role="alert" className="career-error"><p>{error}</p><Button variant="secondary" onClick={() => setReload(value => value + 1)}>Reload opportunities</Button></div>}
    </section>
    <section id="opportunity-reviews" className="card career-panel"><div className="career-section-heading"><h2><Bell size={20} aria-hidden="true" /> Your review reminders</h2><span className="career-badge">{queue.length} pending</span></div>{queue.length ? queue.slice(0, showAllReviews ? queue.length : 3).map(item => <div className="workspace-reminder" key={item.id}><div><strong>{item.company} · {item.role}</strong>{item.profile_revision && <p>Profile version {item.profile_revision} · {item.draft_count ?? 0} saved draft versions</p>}{item.form_status && item.form_status !== 'not_prepared' && <p className="subtle">Employer form: {item.form_status.replaceAll('_', ' ')}</p>}{item.match && <details className="career-details"><summary>Why it matched · {item.match.score}/100</summary><p>{item.match.reason}</p></details>}<p>{item.due_date}{item.due_date < today ? ' · Overdue' : item.due_date === today ? ' · Today' : ''} · {item.note}</p></div><Button variant="secondary" onClick={() => { if (item.workspace_id) onOpenWorkspace(item.workspace_id) }}>Review application</Button></div>) : <p>Your prepared applications and review reminders will appear here.</p>}{queue.length > 3 && <Button variant="secondary" onClick={() => setShowAllReviews(!showAllReviews)}>{showAllReviews ? 'Show fewer reviews' : `Show all ${queue.length} reviews`}</Button>}</section>
    <details id="opportunity-settings" className="card opportunity-settings"><summary>Schedules, email & application settings <span>Configure once; review when ready</span></summary><ApplicationFormSettings /><ReviewPreferences /><DiscoverySchedules resumes={resumes} /><EmailDigest /></details>
    <details className="card opportunity-settings"><summary>Browse public jobs <span>Explore and save without model calls</span></summary><JobCatalog resumes={resumes} onSaved={onOpenWorkspace} /></details>
    <section id="discovery-history" className="card career-panel"><div className="career-section-heading"><div><p className="eyebrow">SAVED ACTIVITY</p><h2>Discovery history</h2></div><span className="career-badge">{batches.length} runs</span></div>
      <div className="run-history-controls"><div className="field"><label htmlFor="run-history-filter">Show runs</label><select id="run-history-filter" value={runFilter} onChange={event => { setRunFilter(event.target.value); setVisibleRuns(5) }}><option value="all">All runs</option><option value="attention">Needs attention</option><option value="active">In progress</option><option value="completed">Completed</option></select></div><div className="field"><label htmlFor="run-history-search">Find company or role</label><input id="run-history-search" type="search" placeholder="Search saved runs…" value={runSearch} onChange={event => { setRunSearch(event.target.value); setVisibleRuns(5) }} /></div></div>
      {!batches.length && <p>No discovery runs yet.</p>}{!!batches.length && !filteredRuns.length && <p>No runs match these filters.</p>}
      {filteredRuns.slice(0, visibleRuns).map((batch, index) => <details className="discovery-run" key={batch.id} open={index === 0 || ['queued', 'running'].includes(batch.status)}><summary><span><strong>{new Date(batch.created_at).toLocaleString()}</strong><small>{batch.progress.items.length} applications · {batch.progress.candidates?.length ?? 0} shortlisted roles</small></span><span className={`run-status run-status--${batch.status}`}>{batch.status.replaceAll('_', ' ')}</span></summary><div className="agent-results">
      {batch.profile_preferences && <section className="agent-requirement" aria-label="Preferences used for this batch"><h4>Preferences used · Profile version {batch.profile_revision}</h4><dl>
        <dt>Target roles</dt><dd>{batch.profile_preferences.target_roles || 'Not specified'}</dd>
        <dt>Locations</dt><dd>{batch.profile_preferences.locations || 'Not specified'}</dd>
        <dt>Work arrangement</dt><dd>{batch.profile_preferences.remote === 'unspecified' ? 'Not specified' : batch.profile_preferences.remote || 'Not specified'}</dd>
        <dt>Exclusions</dt><dd>{batch.profile_preferences.exclusions || 'None specified'}</dd>
      </dl>{batch.progress.reassesses_batch_id && <p className="subtle">This reassessment applies these preferences to the earlier saved listings. It does not search for new jobs. Previously shortlisted roles can now be rejected.</p>}</section>}
      {!['queued', 'running', 'waiting'].includes(batch.status) && batch.progress.error && <p className="field-error">{batch.progress.error}</p>}{batch.progress.source_errors?.map((message, i) => <p key={i}>{message}</p>)}
      {['queued', 'running'].includes(batch.status) && <p role="status">Agents are working independently. If the backend was restarted, resume this saved run.</p>}
      {batch.status === 'partial' && <p>Some applications are incomplete. Review any saved drafts and warnings; deferred applications are not ready to submit.</p>}
      {['waiting', 'failed', 'partial'].includes(batch.status) && (batch.cooldown_until ?? batch.progress.retry_at) ? <CooldownStatus key={`${batch.id}:${batch.cooldown_until ?? batch.progress.retry_at}:${batch.server_time ?? ''}`} until={(batch.cooldown_until ?? batch.progress.retry_at)!} serverTime={batch.server_time} /> : batch.status === 'waiting' ? <p role="status">This batch is paused. Automatic retries are off. No exact cooldown time was recorded; resume when you are ready.</p> : null}
      {batch.progress.items.map(item => { const job = batch.progress.candidates?.find(candidate => candidate.candidate_id === item.candidate_id); return <div className="agent-requirement" key={item.candidate_id}><strong>{job?.company} · {job?.role}</strong><p>{item.status.replaceAll('_', ' ')} · Match score {item.match.score}/100</p><p>{item.match.reason}</p>{item.outcome_reason && <p>{item.outcome_reason}</p>}{item.match.cautions.map((caution, i) => <p key={i}>Check before submitting: {caution}</p>)}{item.error && <p className="field-error">{item.error}</p>}{job && <p>Source: <a href={job.url} target="_blank" rel="noreferrer">{job.source} <ExternalLink size={13} aria-hidden="true" /></a> · {job.location}</p>}{item.workspace_id && <Button variant="secondary" onClick={() => { if (item.workspace_id) onOpenWorkspace(item.workspace_id) }}>Open application workspace</Button>}</div> })}
      {!batch.progress.items.length && batch.status === 'completed' && <p>No new suitable roles were found in this batch. Review your preferences or try again when the feeds refresh.</p>}
      <details className="career-details"><summary>Matching decisions and activity</summary>{(batch.progress.matches ?? batch.progress.match_results ?? []).filter(match => match.score < 70).map(match => <p key={match.candidate_id}>Skipped {batch.progress.candidates?.find(candidate => candidate.candidate_id === match.candidate_id)?.role}: {match.reason}</p>)}<ol>{batch.progress.events.map((message, i) => <li key={i}>{message}</li>)}</ol></details>
      {!!batch.progress.candidates?.length && <Button variant="secondary" disabled={busy || batch.is_running} onClick={async () => {
        setBusy(true); setError('')
        const key = reassessKeys.current[batch.id] ?? crypto.randomUUID()
        reassessKeys.current[batch.id] = key
        try {
          const created = await get<Batch>(`/api/discovery/${batch.id}/reassess`, { request_id: key, review_date: useReminderPreferences ? null : form.review_date })
          setBatches(items => [created, ...items.filter(item => item.id !== created.id)])
          delete reassessKeys.current[batch.id]
          setNotice('Reassessment started with your latest confirmed profile. Previous drafts are preserved. New results and reminders will appear here.')
        } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not reassess saved jobs.') }
        finally { setBusy(false) }
      }}>Reassess saved jobs with latest profile</Button>}
      {(['queued', 'running', 'waiting', 'failed'].includes(batch.status) || batch.progress.items.some(item => item.status === 'deferred') || batch.can_redraft_rejected) && <Button variant="secondary" disabled={busy || batch.is_running || (batch.cooldown_until ?? batch.progress.retry_at ?? 0) > now + clockOffset} onClick={async () => { setBusy(true); try { const updated = await get<Batch>(`/api/discovery/${batch.id}/retry`, {}); setBatches(items => items.map(item => item.id === batch.id ? updated : item)); setReload(value => value + 1) } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not resume saved batch.') } finally { setBusy(false) } }}>{batch.is_running ? 'Batch is running…' : (batch.cooldown_until ?? batch.progress.retry_at ?? 0) > now + clockOffset ? 'Cooldown active…' : batch.can_redraft_rejected ? 'Draft matched jobs previously rejected' : 'Resume saved batch'}</Button>}
    </div></details>)}{filteredRuns.length > visibleRuns && <Button variant="secondary" onClick={() => setVisibleRuns(value => value + 5)}>Show older runs ({filteredRuns.length - visibleRuns} more)</Button>}</section>
  </div>
}
