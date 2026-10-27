import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { z } from 'zod'
import { JOB_STATUSES, jobApplicationInputSchema } from '../../types/models'
import type { JobApplication } from '../../types/models'
import { useAppData } from '../../app/dataContext'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { useToday } from '../../utils/useToday'

const formSchema = jobApplicationInputSchema
export function JobForm({ job, onClose, onSaved }: { job?: JobApplication; onClose: () => void; onSaved: () => void }) {
  const { dispatch, blocked } = useAppData()
  const today = useToday()
  const [values, setValues] = useState(() => ({ company: job?.company ?? '', role: job?.role ?? '', url: job?.url ?? '', status: job?.status ?? 'Saved', applicationDate: job?.applicationDate ?? '', nextAction: job?.nextAction ?? '', reminderDate: job?.reminderDate ?? '', notes: job?.notes ?? '' }))
  const [initial] = useState(values)
  const [discard, setDiscard] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saveError, setSaveError] = useState(false)
  const dirty = JSON.stringify(values) !== JSON.stringify(initial)
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  function submit(event: FormEvent) {
    event.preventDefault()
    const parsed = formSchema.safeParse({ ...values, url: values.url.trim() || undefined, applicationDate: values.applicationDate || undefined, nextAction: values.nextAction.trim() || undefined, reminderDate: values.reminderDate || undefined })
    const issues = parsed.success ? {} : Object.fromEntries(Object.entries(z.flattenError(parsed.error).fieldErrors).map(([key, messages]) => [key, messages?.[0] ?? 'Invalid value']))
    if (values.applicationDate > today) issues.applicationDate = 'The submission date cannot be in the future.'
    if (!parsed.success || Object.keys(issues).length) { setErrors(issues); return }
    const success = job ? dispatch({ type: 'updateJobApplication', id: job.id, input: parsed.data }) : dispatch({ type: 'addJobApplication', input: parsed.data })
    if (success) onSaved(); else setSaveError(true)
  }
  function change(key: keyof typeof values, value: string) { setValues((current) => ({ ...current, [key]: value })) }
  return <Dialog title={discard ? 'Discard unsaved changes?' : job ? 'Edit application' : 'Add application'} closeLabel={discard ? 'Keep editing' : 'Cancel'} onClose={() => { if (discard) setDiscard(false); else if (dirty) setDiscard(true); else onClose() }}>
    {discard ? <><p>Your changes have not been saved.</p><Button variant="danger" onClick={onClose}>Discard changes</Button></> : <form noValidate onSubmit={submit}>
      {(['company', 'role'] as const).map((key) => <Field key={key} id={`job-${key}`} label={key === 'company' ? 'Company' : 'Role'} error={errors[key]}><input id={`job-${key}`} required value={values[key]} onChange={(event) => change(key, event.target.value)} aria-invalid={!!errors[key]} aria-describedby={`job-${key}-help`} /></Field>)}
      <Field id="job-url" label="Job URL (optional)" error={errors.url}><input id="job-url" type="url" value={values.url} onChange={(event) => change('url', event.target.value)} aria-invalid={!!errors.url} aria-describedby="job-url-help" /></Field>
      <Field id="job-status" label="Application status"><select id="job-status" value={values.status} onChange={(event) => change('status', event.target.value)}>{JOB_STATUSES.map((status) => <option key={status}>{status}</option>)}</select></Field>
      <Field id="job-date" label="Application date" error={errors.applicationDate} hint="Date actually submitted. Required for Applied, Interviewing, Offer, and Rejected."><input id="job-date" type="date" max={today} value={values.applicationDate} onChange={(event) => change('applicationDate', event.target.value)} aria-invalid={!!errors.applicationDate} aria-describedby="job-date-help" /></Field>
      <Field id="job-action" label="Next action (optional)" error={errors.nextAction} hint="For example: Finish application, or Follow up with recruiter."><input id="job-action" value={values.nextAction} onChange={(event) => change('nextAction', event.target.value)} aria-invalid={!!errors.nextAction} aria-describedby="job-action-help" /></Field>
      <Field id="job-reminder" label="Reminder date (optional)" error={errors.reminderDate} hint="Due reminders appear on your Dashboard when you open the app."><input id="job-reminder" type="date" value={values.reminderDate} onChange={(event) => change('reminderDate', event.target.value)} aria-invalid={!!errors.reminderDate} aria-describedby="job-reminder-help" /></Field>
      <Field id="job-notes" label="Application notes"><textarea id="job-notes" rows={5} value={values.notes} onChange={(event) => change('notes', event.target.value)} /></Field>
      {saveError && <p role="alert">Could not save. Your entries are still here. Check the storage message and retry.</p>}
      <Button type="submit" disabled={blocked}>Save application</Button>
    </form>}
  </Dialog>
}
