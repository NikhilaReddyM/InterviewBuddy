import { useState } from 'react'
import { useAppData } from '../../app/dataContext'
import { Button } from '../../components/Button'
import { JobForm } from './JobForm'
import { getApplicationReminders } from './calculations'
import { useToday } from '../../utils/useToday'

export function ApplicationReminders() {
  const { data, dispatch, blocked } = useAppData()
  const today = useToday()
  const reminders = getApplicationReminders(data.jobApplications, today)
  const [editId, setEditId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const selected = data.jobApplications.find((job) => job.id === editId)
  return <section className="card dashboard-panel area-panel" aria-labelledby="application-reminders"><h2 id="application-reminders">Application reminders</h2><p className="dashboard-muted">Finish applications and follow up. Reminders appear here when you open the app.</p>
    {[{ label: 'Due today or overdue', jobs: reminders.due }, { label: 'Next 7 days', jobs: reminders.upcoming }].map(({ label, jobs }) => <div className="revision-group" key={label}><h3>{label} ({jobs.length})</h3>{jobs.length === 0 ? <p className="dashboard-muted">No application reminders.</p> : <ul>{jobs.map((job) => <li key={job.id}><strong>{job.company} · {job.role}</strong><span>{job.nextAction} · {job.reminderDate}{job.reminderDate! < today ? ' · Overdue' : ''}</span><div className="actions"><Button variant="secondary" disabled={blocked} onClick={() => setEditId(job.id)}>Open application / reschedule</Button><Button variant="secondary" disabled={blocked} onClick={() => {
      if (dispatch({ type: 'completeApplicationReminder', id: job.id })) setNotice('Reminder completed. Application status is unchanged.'); else setNotice('Could not complete reminder. Check the storage message.')
    }}>Mark reminder done</Button></div></li>)}</ul>}</div>)}<p role="status">{notice}</p>
    {selected && <JobForm job={selected} onClose={() => setEditId(null)} onSaved={() => { setEditId(null); setNotice('Application and reminder saved.') }} />}
  </section>
}
