import { useEffect, useState } from 'react'
import { Sparkles, MessageCircle, RotateCcw } from 'lucide-react'
import { Button } from '../../components/Button'

type Fact = { text: string; evidence?: string; question?: string }
type Claim = { text: string; source_ids: string[] }
type Run = {
  id: string; checkpoint_id: string; paused: boolean; error?: string | null; next: string[]
  state: {
    phase?: string; events?: string[]; decision?: { action: string; reason: string; questions: string[] }
    analysis?: { summary: string; requirements: { text: string; job_quote: string; relevant_fact_ids: string[]; gap: string }[]; missing_facts: string[]; concerns: string[] }
    review?: { summary: string; findings: { severity: string; artifact: string; message: string }[] }
    context?: { facts: Record<string, Fact> }
    answers?: { id: string; question: string; answer: string }[]
    package?: { cover_letter: Claim[]; resume_suggestions: Claim[]; screening_answers: { question: string; answer: string | null; source_ids: string[] }[] }
  }
}
type SavedRun = { id: string; workflow?: string }
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(body) })
  if (!response.ok) {
    const value = await response.json().catch(() => ({})) as { detail?: unknown }
    throw new Error(typeof value.detail === 'string' ? value.detail : 'Could not complete the request. Your saved run is available below.')
  }
  return response.json() as Promise<T>
}
const phaseLabels: Record<string, string> = {
  starting: 'Starting', analyzed: 'Requirements analyzed', coordinating: 'Choosing next step', clarified: 'Answers saved', reassessing: 'Reassessing your answers', drafted: 'Drafts prepared', reviewed: 'Review complete',
  ready_for_review: 'Ready for your review', needs_review: 'Needs your attention', role_not_recommended: 'Role not recommended',
}

export function AgentFlowPanel({ workspaceId, runs, onSaved }: { workspaceId: string; runs: SavedRun[]; onSaved: () => Promise<void> }) {
  const [run, setRun] = useState<Run | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [instructions, setInstructions] = useState('')
  const [screening, setScreening] = useState('')
  const [answers, setAnswers] = useState<string[]>([])
  const [confirmed, setConfirmed] = useState(false)
  const [requestId, setRequestId] = useState(() => crypto.randomUUID())
  const saved = runs.filter(item => item.workflow === 'application_v1')
  const base = `/api/workspaces/${workspaceId}`
  const dirty = !!(instructions || screening || answers.some(answer => answer.trim()))
  useEffect(() => {
    if (!dirty) return
    const navigate = (event: Event) => { if (!window.confirm('Discard unsaved agent instructions or answers?')) event.preventDefault() }
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('interviewbuddy:before-navigate', navigate)
    window.addEventListener('beforeunload', unload)
    window.addEventListener('interviewbuddy:before-workspace-change', navigate)
    return () => { window.removeEventListener('interviewbuddy:before-navigate', navigate); window.removeEventListener('beforeunload', unload); window.removeEventListener('interviewbuddy:before-workspace-change', navigate) }
  }, [dirty])
  async function action(work: () => Promise<Run>) {
    setBusy(true); setError('')
    try { const result = await work(); setRun(result); setAnswers([]); setConfirmed(false); await onSaved() }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Request failed. Reopen the saved run and retry.') }
    finally { setBusy(false) }
  }
  async function load(runId: string) {
    if (answers.some(answer => answer.trim()) && !window.confirm('Discard unsaved answers and reload the run?')) return
    await action(() => request<Run>(`${base}/runs/${runId}`))
  }
  const sourceFacts: Record<string, Fact> = { ...run?.state.context?.facts }
  run?.state.answers?.forEach(answer => { sourceFacts[answer.id] = { text: answer.answer, question: answer.question } })
  const questions = run?.paused ? run.state.decision?.questions ?? [] : []
  function evidence(ids: string[]) {
    return ids.length ? <details className="career-details"><summary>Supporting facts ({ids.length})</summary>{ids.map(sourceId => <blockquote key={sourceId}><p>{sourceFacts[sourceId]?.text ?? 'Source unavailable'}</p>{sourceFacts[sourceId]?.evidence && <small>Resume: {sourceFacts[sourceId].evidence}</small>}{sourceFacts[sourceId]?.question && <small>Your answer to: {sourceFacts[sourceId].question}</small>}</blockquote>)}</details> : null
  }
  return <section className="agent-panel" aria-busy={busy}>
    <div className="career-section-heading"><div><p className="eyebrow">APPLICATION COPILOT</p><h3>Prepare an application with your agents</h3></div><Sparkles size={24} aria-hidden="true" /></div>
    <p>Analyze this role, prepare application materials, and check claims against the profile saved with this workspace. The coordinator works independently, flags missing facts for your final review, revises drafts, or recommends skipping the role.</p>
    <p className="subtle">Starting sends the job description, profile facts, preferences, and your instructions to your configured model provider. Answers you provide are used in this run; your Career Profile stays unchanged. Nothing is submitted.</p>
    <details className="career-details" open={!run}><summary>Start a new agent run</summary><form onSubmit={event => { event.preventDefault(); void action(async () => {
      const result = await request<Run>(`${base}/agent-runs`, { request_id: requestId, instructions, autonomous: true, screening_questions: screening.split('\n').map(value => value.trim()).filter(Boolean) })
      setInstructions(''); setScreening(''); setRequestId(crypto.randomUUID()); return result
    }) }}><fieldset className="workspace-fields" disabled={busy}><div className="field"><label htmlFor="agent-instructions">Application instructions (optional)</label><textarea id="agent-instructions" rows={2} maxLength={5000} value={instructions} onChange={event => { setInstructions(event.target.value); setRequestId(crypto.randomUUID()) }} placeholder="For example: keep the cover letter concise." /></div><div className="field"><label htmlFor="agent-screening">Additional screening questions (one per line, optional)</label><textarea id="agent-screening" rows={3} value={screening} onChange={event => { setScreening(event.target.value); setRequestId(crypto.randomUUID()) }} /><p className="field-hint">Questions included in the job description are also extracted. Unknown answers remain flagged for you.</p></div><Button type="submit"><Sparkles size={17} />Prepare application</Button></fieldset></form></details>
    {busy && <p role="status">Agents are working. This may take several minutes. Completed steps are saved so you can reopen the run if the connection drops.</p>}
    {saved.length > 0 && <div className="actions">{saved.map((item, index) => <Button key={item.id} variant="secondary" disabled={busy} onClick={() => void load(item.id)}>Open agent run {index + 1}</Button>)}</div>}
    {error && <div className="career-error" role="alert"><h3>We couldn’t complete that request</h3><p>{error}</p><p>Your completed steps remain saved. Reopen the latest run below or retry the same action.</p><Button disabled={busy} variant="secondary" onClick={() => void onSaved().catch(() => setError('Could not reload saved runs. Check the backend connection.'))}>Reload saved run list</Button></div>}
    {run && <div className="agent-results"><div className="career-section-heading"><h3>{run.paused ? 'A few details are needed' : phaseLabels[run.state.phase ?? ''] ?? 'Run saved'}</h3><span className="career-badge">{run.id.slice(0, 8)}</span></div>
      {run.state.decision && <p>{run.state.decision.reason}</p>}
      {run.error && <div className="career-error" role="alert"><h3>A step needs to be retried</h3><p>{run.error}</p><p>Completed work is saved. Retry continues at {run.next[0]?.replaceAll('_', ' ') || 'the pending step'}.</p>{!run.paused && run.next.length > 0 && <Button disabled={busy} onClick={() => void action(() => request<Run>(`${base}/agent-runs/${run.id}/retry`, { checkpoint_id: run.checkpoint_id }))}><RotateCcw size={16} />Retry failed step</Button>}<Button disabled={busy} variant="secondary" onClick={() => void load(run.id)}>Reload run</Button></div>}
      {questions.length > 0 && <form onSubmit={event => { event.preventDefault(); void action(() => request<Run>(`${base}/agent-runs/${run.id}/resume`, { checkpoint_id: run.checkpoint_id, answers })) }}><fieldset disabled={busy} className="workspace-fields"><p>Answer each question, or enter “unknown.” Your answers become run-specific facts the agents may use in drafts.</p>{questions.map((question, index) => <div className="field" key={index}><label htmlFor={`agent-answer-${index}`}>{question}</label><textarea id={`agent-answer-${index}`} required maxLength={5000} rows={2} value={answers[index] ?? ''} onChange={event => { const next = [...answers]; next[index] = event.target.value; setAnswers(next); setConfirmed(false) }} /></div>)}<label className="agent-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />Use these answers in my application drafts</label><Button type="submit" disabled={!confirmed || questions.some((_, i) => !answers[i]?.trim())}><MessageCircle size={16} />Save answers and continue</Button></fieldset></form>}
      {run.state.analysis && <details className="career-details" open><summary>Role analysis</summary><p>{run.state.analysis.summary}</p>{run.state.analysis.requirements.map((item, index) => <div className="agent-requirement" key={index}><strong>{item.text}</strong><p className="subtle">Job evidence: {item.job_quote}</p>{item.gap && <p>Gap or uncertainty: {item.gap}</p>}{evidence(item.relevant_fact_ids)}</div>)}{run.state.analysis.missing_facts.map((item, i) => <p key={i}>Missing information: {item}</p>)}{run.state.analysis.concerns.map((item, i) => <p key={i}>Concern: {item}</p>)}</details>}
      {run.state.package && <><p className="subtle">These are editable drafts for your review. Inspect the evidence and review findings before using them.</p>{(['cover_letter', 'resume_suggestions'] as const).map(kind => <details className="career-details" key={kind} open={kind === 'cover_letter'}><summary>{kind === 'cover_letter' ? 'Cover letter' : 'Resume suggestions'}</summary>{run.state.package?.[kind].map((claim, index) => <div key={index}><p className="agent-draft-text">{claim.text}</p>{evidence(claim.source_ids)}</div>)}</details>)}<details className="career-details"><summary>Screening answers</summary>{run.state.package.screening_answers.length ? run.state.package.screening_answers.map((answer, index) => <div key={index}><strong>{answer.question}</strong><p>{answer.answer ?? 'Needs your answer — not enough confirmed information.'}</p>{evidence(answer.source_ids)}</div>) : <p>No screening questions were available.</p>}</details></>}
      {run.state.review?.summary && <details className="career-details" open><summary>Reviewer findings</summary><p>{run.state.review.summary}</p>{run.state.review.findings.map((finding, index) => <p key={index}><strong>{finding.severity}</strong> · {finding.artifact.replaceAll('_', ' ')}: {finding.message}</p>)}{!run.state.review.findings.length && <p>No issues were flagged by the reviewer. Please check the drafts yourself before using them.</p>}</details>}
      {!!run.state.events?.length && <details className="career-details"><summary>Agent activity</summary><ol>{run.state.events.map((item, index) => <li key={index}>{item}</li>)}</ol></details>}
    </div>}
  </section>
}
