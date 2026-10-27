import { useState } from 'react'
import { useAppData } from '../../app/dataContext'
import { JOB_STATUSES } from '../../types/models'
import { useToday } from '../../utils/useToday'
import { Button } from '../../components/Button'
import { Field } from '../../components/Field'
import { EmptyState } from '../../components/EmptyState'
import { ConfirmDialog } from '../../components/Dialog'
import { JobForm } from './JobForm'
import { getApplicationSummary } from './calculations'
import './jobs.css'

export function JobApplications() {
  const { data, dispatch, blocked } = useAppData()
  const today = useToday()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [dueOnly, setDueOnly] = useState(false)
  const [sort, setSort] = useState('updated')
  const [editor, setEditor] = useState<{ type: 'add' | 'edit' | 'delete'; id?: string } | null>(null)
  const [notice, setNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const selected = data.jobApplications.find((job) => job.id === editor?.id)
  const summary = getApplicationSummary(data.jobApplications, today)
  const query = search.trim().toLocaleLowerCase()
  const jobs = data.jobApplications.filter((job) => (!query || `${job.company} ${job.role} ${job.notes} ${job.nextAction ?? ''}`.toLocaleLowerCase().includes(query)) && (!status || job.status === status) && (!dueOnly || !!job.reminderDate && job.reminderDate <= today))
    .sort((a, b) => sort === 'application' ? (b.applicationDate ?? '').localeCompare(a.applicationDate ?? '') || a.company.localeCompare(b.company) : sort === 'reminder' ? (a.reminderDate ?? '9999-99-99').localeCompare(b.reminderDate ?? '9999-99-99') || a.company.localeCompare(b.company) : b.updatedAt.localeCompare(a.updatedAt) || a.company.localeCompare(b.company))
  function saved(message: string) { setEditor(null); setNotice(message) }
  function clear() { setSearch(''); setStatus(''); setDueOnly(false); setSort('updated') }
  return <div className="jobs-page"><div className="jobs-toolbar"><p>Your job search, all in one place. Enter applications manually and set your next step.</p><Button disabled={blocked} onClick={() => setEditor({ type: 'add' })}>Add application</Button></div>
    <section className="card jobs-metrics" aria-label="Application summary">{[
      ['Applied this week', summary.week], ['Applied this month', summary.month], ['Applied overall', summary.total], ['Unfinished applications', summary.unfinished], ['Interviewing', summary.interviewing],
    ].map(([label, count]) => <div key={label}><strong>{count}</strong><span>{label}</span></div>)}</section><p className="jobs-muted">Submission counts use the recorded application date, through today. Rejected and withdrawn applications remain in historical counts.</p>
    <section className="card jobs-filters" aria-label="Application filters"><Field id="job-search" label="Search applications"><input id="job-search" type="search" placeholder="Company, role, notes, or next action" value={search} onChange={(event) => setSearch(event.target.value)} /></Field><Field id="job-filter" label="Filter application status"><select id="job-filter" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option>{JOB_STATUSES.map((value) => <option key={value}>{value}</option>)}</select></Field><Field id="job-sort" label="Sort applications"><select id="job-sort" value={sort} onChange={(event) => setSort(event.target.value)}><option value="updated">Recently updated</option><option value="application">Newest application date</option><option value="reminder">Next reminder first</option></select></Field><label className="jobs-due-filter"><input type="checkbox" checked={dueOnly} onChange={(event) => setDueOnly(event.target.checked)} />Due reminders only</label><Button variant="secondary" onClick={clear}>Clear filters</Button></section>
    <p className="jobs-muted" aria-live="polite">{jobs.length} of {data.jobApplications.length} applications</p><p role="status" className="jobs-notice">{notice}</p>
    {data.jobApplications.length === 0 ? <section className="card"><EmptyState title="Start tracking your job search" action={<Button disabled={blocked} onClick={() => setEditor({ type: 'add' })}>Enter your first application</Button>}>Add a role you have applied to, or save one to finish later. Set a reminder for the next step.</EmptyState></section> : jobs.length === 0 ? <section className="card"><EmptyState title="No matching applications" action={<Button variant="secondary" onClick={clear}>Reset application filters</Button>}>Try another search or broaden your filters.</EmptyState></section> : <div className="jobs-list">{jobs.map((job) => <article className="card job-card" key={job.id} aria-label={`${job.company} · ${job.role}`}><div className="job-heading"><h2>{job.company}</h2><span className="pill">{job.status}</span></div><h3>{job.role}</h3><p className="jobs-muted">{job.applicationDate ? `Applied: ${job.applicationDate}` : 'Not submitted yet'}</p>{job.url && <a href={job.url} target="_blank" rel="noopener noreferrer">Open application page ↗</a>}{job.nextAction && <p><strong>Next action:</strong> {job.nextAction}</p>}{job.reminderDate && <p className={job.reminderDate <= today ? 'jobs-overdue' : 'jobs-muted'}>Reminder: {job.reminderDate}{job.reminderDate < today ? ' · Overdue' : job.reminderDate === today ? ' · Today' : ''}</p>}{job.notes && <details><summary>Read application notes</summary><p className="job-notes">{job.notes}</p></details>}<div className="actions"><Button variant="secondary" disabled={blocked} onClick={() => setEditor({ type: 'edit', id: job.id })}>Edit application / reminder</Button>{job.reminderDate && <Button variant="secondary" disabled={blocked} onClick={() => {
      if (dispatch({ type: 'completeApplicationReminder', id: job.id })) setNotice('Reminder completed. Application status is unchanged.'); else setNotice('Could not save. Check the storage message.')
    }}>Mark reminder done</Button>}<Button variant="danger" disabled={blocked} onClick={() => { setActionError(''); setEditor({ type: 'delete', id: job.id }) }}>Delete application</Button></div></article>)}</div>}
    {editor?.type === 'add' && <JobForm onClose={() => setEditor(null)} onSaved={() => saved('Application saved. Clear filters if it is hidden.')} />}
    {editor?.type === 'edit' && selected && <JobForm job={selected} onClose={() => setEditor(null)} onSaved={() => saved('Application updated.')} />}
    {editor?.type === 'delete' && selected && <ConfirmDialog title="Delete application?" confirmLabel="Delete permanently" onClose={() => setEditor(null)} onConfirm={() => {
      if (dispatch({ type: 'deleteJobApplication', id: selected.id })) saved('Application deleted.'); else setActionError('Could not delete. Check the storage message and retry.')
    }}><p>Delete {selected.company} · {selected.role}, its notes, and reminder? This cannot be undone and removes it from your counts.</p>{actionError && <p role="alert">{actionError}</p>}</ConfirmDialog>}
  </div>
}
