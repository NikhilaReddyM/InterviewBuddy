import { useState } from 'react'
import { useAppData } from '../../app/dataContext'
import type { Screen } from '../../types/models'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ConfirmDialog } from '../../components/Dialog'
import { CompletionForm, SessionForm } from '../planner/PlannerForms'
import { localDate } from '../../utils/dates'
import { useToday } from '../../utils/useToday'
import { getAreaProgress, getRevisionQueue, getTodaySessions, getWeeklySummary } from './calculations'
import './dashboard.css'
import { ApplicationReminders } from '../jobs/ApplicationReminders'
import { getApplicationSummary } from '../jobs/calculations'

type Editor = { type: 'add' } | { type: 'complete' | 'undo'; id: string }
export function Dashboard({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const { data, dispatch, blocked } = useAppData()
  const today = useToday()
  const [editor, setEditor] = useState<Editor | null>(null)
  const [notice, setNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const applications = getApplicationSummary(data.jobApplications, today)
  const sessions = getTodaySessions(data, today)
  const weekly = getWeeklySummary(data, today)
  const areas = getAreaProgress(data, today)
  const revisions = getRevisionQueue(data, today)
  const selected = editor && 'id' in editor ? data.sessions.find((session) => session.id === editor.id) : undefined
  function saved(message: string) { setEditor(null); setNotice(message); setActionError('') }
  const format = (date: string) => localDate(date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return <div className="dashboard">
    <div className="dashboard-toolbar"><p>{localDate(today).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</p><div className="actions"><Button disabled={blocked} onClick={() => setEditor({ type: 'add' })}>Add session</Button><Button variant="secondary" onClick={() => onNavigate('opportunities')}>Review applications</Button><Button variant="secondary" onClick={() => onNavigate('resources')}>Save a resource</Button><Button variant="secondary" onClick={() => onNavigate('design-lab')}>Practice system design</Button></div></div>
    <section className="card dashboard-week" aria-label="Weekly summary"><div className="dashboard-section-heading"><h2>This week</h2><span>{format(weekly.weekStart)} – {format(weekly.weekEnd)}</span></div><div className="dashboard-metrics">
      <div><strong>{weekly.plannedMinutes}</strong><span>Planned minutes</span></div><div><strong>{weekly.completedMinutes}</strong><span>Completed minutes (actual)</span></div><div><strong>{weekly.availableMinutes}</strong><span>Available minutes</span></div><div><strong>{weekly.completedSessions} / {weekly.scheduledSessions}</strong><span>Sessions completed · {weekly.completionPercent}%</span></div>
    </div><p className="dashboard-muted">Totals follow each session’s scheduled date. Actual minutes can exceed the plan.</p><Button variant="secondary" onClick={() => onNavigate('planner')}>Open weekly planner</Button></section>
    <p role="status" className="dashboard-notice">{notice}</p>
    <section className="card dashboard-panel" aria-labelledby="job-summary-title"><h2 id="job-summary-title">Job search snapshot</h2><p className="dashboard-muted">{applications.week} applied this week · {applications.month} this month · {applications.total} overall · {applications.unfinished} unfinished · {applications.interviewing} interviewing</p><Button variant="secondary" onClick={() => onNavigate('jobs')}>Track job applications</Button></section>
    <ApplicationReminders />
    <div className="dashboard-columns"><section className="card dashboard-panel" aria-labelledby="today-title"><h2 id="today-title">Today’s sessions</h2>
      {sessions.length === 0 ? <EmptyState title="A fresh space for today" action={<Button disabled={blocked} onClick={() => setEditor({ type: 'add' })}>Plan today’s first session</Button>}>Add a focused study block, or take a planned rest day.</EmptyState> : <div className="dashboard-session-list">{sessions.map((session) => <article key={session.id} aria-label={session.topic} className="dashboard-session"><div className="dashboard-section-heading"><h3>{session.topic}</h3><span className="pill">{session.completion ? 'Completed' : 'Planned'}</span></div><p>{session.area} · {session.plannedMinutes} min planned{session.completion && ` · ${session.completion.actualMinutes} min actual`}</p>{session.resourceUrl && <a href={session.resourceUrl} target="_blank" rel="noopener noreferrer">Open resource ↗</a>}<div className="actions"><Button variant="secondary" disabled={blocked} onClick={() => setEditor({ type: 'complete', id: session.id })}>{session.completion ? 'Edit completion' : 'Mark complete'}</Button>{session.completion && <Button variant="secondary" disabled={blocked} onClick={() => { setActionError(''); setEditor({ type: 'undo', id: session.id }) }}>Undo completion</Button>}</div></article>)}</div>}
    </section>
    <section className="card dashboard-panel" aria-labelledby="revision-title"><h2 id="revision-title">Revision queue</h2><p className="dashboard-muted">Due dates stay under your control. Completing a session does not reschedule revision.</p>
      {revisions.due.length === 0 && revisions.upcoming.length === 0 ? <EmptyState title="No revisions due soon" action={<Button variant="secondary" onClick={() => onNavigate('resources')}>Open resource library</Button>}>Set a next revision date on a saved resource to see reminders here.</EmptyState> : <>{[{ title: 'Due today or overdue', items: revisions.due }, { title: 'Next 7 days', items: revisions.upcoming }].map(({ title, items }) => <div key={title} className="revision-group"><h3>{title} ({items.length})</h3>{items.length === 0 ? <p className="dashboard-muted">Nothing scheduled.</p> : <ul>{items.map((resource) => <li key={resource.id}><strong>{resource.title}</strong><span>{resource.area} · {format(resource.nextRevisionDate!)}{resource.nextRevisionDate! < today ? ' · Overdue' : resource.nextRevisionDate === today ? ' · Today' : ''}</span></li>)}</ul>}</div>)}<Button variant="secondary" onClick={() => onNavigate('resources')}>Manage revisions</Button></>}
    </section></div>
    <section className="card dashboard-panel area-panel" aria-labelledby="areas-title"><h2 id="areas-title">Progress by preparation area</h2><p className="dashboard-muted">This week’s completed sessions versus scheduled sessions. Activity reflects practice, not interview readiness.</p><div className="area-list">{areas.map((area) => <div key={area.area} className="area-row"><div className="dashboard-section-heading"><h3>{area.area}</h3><span>{area.completedSessions} / {area.scheduledSessions} sessions</span></div><progress max={100} value={area.completionPercent} aria-label={`${area.area} session completion`} /><p>{area.plannedMinutes} min planned · {area.completedMinutes} min actual{area.scheduledSessions === 0 ? ' · No sessions this week' : ` · ${area.completionPercent}% complete`}</p></div>)}</div></section>
    {editor?.type === 'add' && <SessionForm date={today} onClose={() => setEditor(null)} onSaved={(date) => saved(`Session saved for ${date}.`)} />}
    {editor?.type === 'complete' && selected && <CompletionForm session={selected} onClose={() => setEditor(null)} onSaved={() => saved('Completion saved. Progress updated.')} />}
    {editor?.type === 'undo' && selected && <ConfirmDialog title="Undo completion?" confirmLabel="Clear completion" onClose={() => setEditor(null)} onConfirm={() => {
      if (dispatch({ type: 'undoCompletion', id: selected.id })) saved('Completion cleared. Progress updated.')
      else setActionError('Could not save this change. Check the storage message and retry.')
    }}><p>Actual minutes, takeaways, and confidence will be cleared. The session stays in your plan.</p>{actionError && <p role="alert">{actionError}</p>}</ConfirmDialog>}
  </div>
}
