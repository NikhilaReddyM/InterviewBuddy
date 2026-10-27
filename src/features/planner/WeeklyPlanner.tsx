import { useState } from 'react'
import { useAppData } from '../../app/dataContext'
import { Button } from '../../components/Button'
import { ConfirmDialog } from '../../components/Dialog'
import { AvailabilityForm, CompletionForm, SessionForm } from './PlannerForms'
import { addDays, calendarDate, getDailyPlannedMinutes, getEffectiveAvailability, getWeekDates, getWeekStart, localDate } from '../../utils/dates'
import './planner.css'
import { getWeeklySummary } from '../dashboard/calculations'

type Editor = { type: 'session'; id?: string; date: string } | { type: 'completion' | 'delete' | 'undo'; id: string } | { type: 'availability'; date: string }
const formatDate = (date: string) => localDate(date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })

export function WeeklyPlanner() {
  const { data, blocked, dispatch } = useAppData()
  const [today] = useState(() => calendarDate(new Date()))
  const [week, setWeek] = useState(() => getWeekStart(today))
  const [editor, setEditor] = useState<Editor | null>(null)
  const [notice, setNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const dates = getWeekDates(week)
  const sessions = data.sessions.filter((session) => dates.includes(session.date))
  const { plannedMinutes: planned, completedMinutes: actual, availableMinutes: available } = getWeeklySummary(data, week)
  const selected = editor && 'id' in editor ? data.sessions.find((session) => session.id === editor.id) : undefined
  function saved(message: string) { setEditor(null); setNotice(message); setActionError('') }
  function open(next: Editor) { setEditor(next); setActionError('') }
  return <div className="planner">
    <div className="planner-toolbar"><div className="actions"><Button variant="secondary" aria-label="Previous week" onClick={() => setWeek(addDays(week, -7))}>←</Button><Button variant="secondary" onClick={() => setWeek(getWeekStart(today))}>This week</Button><Button variant="secondary" aria-label="Next week" onClick={() => setWeek(addDays(week, 7))}>→</Button></div><h2 aria-live="polite">{formatDate(week)} – {formatDate(dates[6])}</h2><Button disabled={blocked} onClick={() => open({ type: 'session', date: dates.includes(today) ? today : week })}>Add session</Button></div>
    <div className="planner-summary" aria-label="Weekly summary"><div><strong>{planned}</strong><span>Planned minutes</span></div><div><strong>{actual}</strong><span>Completed minutes</span></div><div><strong>{available}</strong><span>Available minutes</span></div><div><strong>{sessions.filter((session) => session.completion).length} / {sessions.length}</strong><span>Sessions completed</span></div></div>
    <p role="status" className="planner-notice">{notice}</p>
    <div className="week-days">{dates.map((date) => {
      const daySessions = sessions.filter((session) => session.date === date)
      const capacity = getEffectiveAvailability(date, data)
      const total = getDailyPlannedMinutes(date, sessions)
      return <section className={`card day-card ${date === today ? 'day-today' : ''}`} key={date} aria-label={date}>
        <div className="day-heading"><div><h3>{localDate(date).toLocaleDateString(undefined, { weekday: 'long' })}{date === today && <span className="pill">Today</span>}</h3><p>{formatDate(date)}</p></div><Button variant="secondary" disabled={blocked} aria-label={`Edit availability for ${date}`} onClick={() => open({ type: 'availability', date })}>{capacity} min available</Button></div>
        <p className={total > capacity ? 'capacity-warning' : 'day-total'}>{total} min planned{total > capacity ? ` · ${total - capacity} min over availability` : ` · ${capacity - total} min remaining`}</p>
        {daySessions.length === 0 && <p className="day-empty">No sessions planned. Leave room to rest, or add a focused study block.</p>}
        <div className="day-sessions">{daySessions.map((session) => <article className="session-card" key={session.id} aria-label={session.topic}>
          <div className="session-heading"><h4>{session.topic}</h4><span className="pill">{session.completion ? 'Completed' : 'Planned'}</span></div>
          <p className="session-meta">{session.area} · {session.plannedMinutes} min planned{session.completion && ` · ${session.completion.actualMinutes} min actual`}</p>
          {session.resourceUrl && <a href={session.resourceUrl} target="_blank" rel="noopener noreferrer">Open resource ↗</a>}
          {session.completion && <div className="completion-details"><p>Confidence: {session.completion.confidence} / 5</p>{session.completion.takeaways && <p className="takeaways">{session.completion.takeaways}</p>}</div>}
          <div className="actions"><Button variant="secondary" disabled={blocked} onClick={() => open({ type: 'session', id: session.id, date })}>Edit session</Button><Button variant="secondary" disabled={blocked} onClick={() => open({ type: 'completion', id: session.id })}>{session.completion ? 'Edit completion' : 'Mark complete'}</Button>{session.completion && <Button variant="secondary" disabled={blocked} onClick={() => open({ type: 'undo', id: session.id })}>Undo completion</Button>}<Button variant="danger" disabled={blocked} onClick={() => open({ type: 'delete', id: session.id })}>Delete session</Button></div>
        </article>)}</div>
        <Button variant="secondary" disabled={blocked} aria-label={`Add session for ${date}`} onClick={() => open({ type: 'session', date })}>+ Add session</Button>
      </section>
    })}</div>
    {editor?.type === 'session' && <SessionForm session={selected} date={editor.date} onClose={() => setEditor(null)} onSaved={(date) => { setWeek(getWeekStart(date)); saved('Session saved.') }} />}
    {editor?.type === 'completion' && selected && <CompletionForm session={selected} onClose={() => setEditor(null)} onSaved={() => saved('Completion saved. Weekly progress updated.')} />}
    {editor?.type === 'availability' && <AvailabilityForm date={editor.date} minutes={getEffectiveAvailability(editor.date, data)} hasOverride={Object.hasOwn(data.availabilityOverrides, editor.date)} onClose={() => setEditor(null)} onSaved={() => saved('Availability saved.')} />}
    {(editor?.type === 'delete' || editor?.type === 'undo') && selected && <ConfirmDialog title={editor.type === 'delete' ? 'Delete study session?' : 'Undo completion?'} confirmLabel={editor.type === 'delete' ? 'Delete permanently' : 'Clear completion'} onClose={() => setEditor(null)} onConfirm={() => {
      if (dispatch({ type: editor.type === 'delete' ? 'deleteSession' : 'undoCompletion', id: selected.id })) saved(editor.type === 'delete' ? 'Session deleted.' : 'Completion cleared. Session is planned again.')
      else setActionError('Could not save this change. Check the storage message and retry.')
    }}><p>{editor.type === 'delete' ? `Delete “${selected.topic}” and all of its completion details? This cannot be undone.` : 'Actual minutes, takeaways, and confidence will be cleared. The session will remain in your plan.'}</p>{actionError && <p role="alert">{actionError}</p>}</ConfirmDialog>}
  </div>
}
