import { useState } from 'react'
import type { FormEvent } from 'react'
import { z } from 'zod'
import { PREPARATION_AREAS, studySessionSchema, sessionCompletionSchema, availabilitySchema } from '../../types/models'
import type { StudySession } from '../../types/models'
import type { SessionInput } from '../../app/dataActions'
import { useAppData } from '../../app/dataContext'
import { Button } from '../../components/Button'
import { Field } from '../../components/Field'
import { Dialog } from '../../components/Dialog'

const sessionFormSchema = studySessionSchema.omit({ id: true, createdAt: true, updatedAt: true, completion: true })
const completionFormSchema = sessionCompletionSchema.omit({ completedAt: true })

export function SessionForm({ session, initial, date, onClose, onSaved }: {
  session?: StudySession; initial?: Partial<SessionInput>; date: string; onClose: () => void; onSaved: (date: string) => void
}) {
  const { dispatch, blocked } = useAppData()
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saveError, setSaveError] = useState(false)
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const input = {
      topic: fields.get('topic'), area: fields.get('area'), date: fields.get('date'),
      plannedMinutes: Number(fields.get('plannedMinutes')),
      resourceUrl: String(fields.get('resourceUrl')).trim() || undefined,
      resourceId: session?.resourceId ?? initial?.resourceId,
    }
    const parsed = sessionFormSchema.safeParse(input)
    if (!parsed.success) { setErrors(Object.fromEntries(Object.entries(z.flattenError(parsed.error).fieldErrors).map(([key, messages]) => [key, messages?.[0] ?? 'Invalid value']))); return }
    const value: SessionInput = parsed.data
    const success = session
      ? dispatch({ type: 'updateSession', id: session.id, input: value })
      : dispatch({ type: 'addSession', input: value })
    if (success) onSaved(value.date)
    else setSaveError(true)
  }
  return <Dialog title={session ? 'Edit study session' : 'Add study session'} onClose={onClose}>
    <form onSubmit={submit} noValidate>
      <Field id="topic" label="Topic" error={errors.topic}><input id="topic" name="topic" defaultValue={session?.topic ?? initial?.topic ?? ''} required aria-invalid={!!errors.topic} aria-describedby="topic-help" /></Field>
      <Field id="area" label="Preparation area"><select id="area" name="area" defaultValue={session?.area ?? initial?.area ?? 'Coding'}>{PREPARATION_AREAS.map((area) => <option key={area}>{area}</option>)}</select></Field>
      <Field id="session-date" label="Date" error={errors.date}><input id="session-date" name="date" type="date" defaultValue={session?.date ?? date} required aria-invalid={!!errors.date} aria-describedby="session-date-help" /></Field>
      <Field id="planned-minutes" label="Planned minutes" error={errors.plannedMinutes} hint="1–1440 whole minutes."><input id="planned-minutes" name="plannedMinutes" type="number" min="1" max="1440" step="1" defaultValue={session?.plannedMinutes ?? initial?.plannedMinutes ?? 60} required aria-invalid={!!errors.plannedMinutes} aria-describedby="planned-minutes-help" /></Field>
      <Field id="resource-url" label="Resource link (optional)" error={errors.resourceUrl}><input id="resource-url" name="resourceUrl" type="url" defaultValue={session?.resourceUrl ?? initial?.resourceUrl ?? ''} placeholder="https://…" aria-invalid={!!errors.resourceUrl} aria-describedby="resource-url-help" /></Field>
      {saveError && <p role="alert">Could not save. Your entries are still here. Check the storage message and retry.</p>}
      <Button type="submit" disabled={blocked}>Save session</Button>
    </form>
  </Dialog>
}

export function CompletionForm({ session, onClose, onSaved }: { session: StudySession; onClose: () => void; onSaved: () => void }) {
  const { dispatch, blocked } = useAppData()
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saveError, setSaveError] = useState(false)
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const parsed = completionFormSchema.safeParse({
      actualMinutes: Number(fields.get('actualMinutes')), takeaways: fields.get('takeaways'),
      confidence: Number(fields.get('confidence')),
    })
    if (!parsed.success) { setErrors(Object.fromEntries(Object.entries(z.flattenError(parsed.error).fieldErrors).map(([key, messages]) => [key, messages?.[0] ?? 'Invalid value']))); return }
    if (dispatch({ type: 'completeSession', id: session.id, input: parsed.data })) onSaved()
    else setSaveError(true)
  }
  return <Dialog title={session.completion ? 'Edit completion' : 'Complete session'} onClose={onClose}>
    <p>{session.topic}</p><form noValidate onSubmit={submit}>
      <Field id="actual-minutes" label="Actual minutes" error={errors.actualMinutes}><input id="actual-minutes" name="actualMinutes" type="number" min="1" max="1440" step="1" defaultValue={session.completion?.actualMinutes ?? session.plannedMinutes} required aria-invalid={!!errors.actualMinutes} aria-describedby="actual-minutes-help" /></Field>
      <Field id="takeaways" label="Takeaways (optional)"><textarea id="takeaways" name="takeaways" rows={4} defaultValue={session.completion?.takeaways ?? ''} /></Field>
      <Field id="confidence" label="Confidence" error={errors.confidence}><select id="confidence" name="confidence" defaultValue={session.completion?.confidence ?? ''} required aria-invalid={!!errors.confidence} aria-describedby="confidence-help"><option value="">Choose confidence</option>{[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} / 5</option>)}</select></Field>
      {saveError && <p role="alert">Could not save completion. Check the storage message and retry.</p>}
      <Button type="submit" disabled={blocked}>Save completion</Button>
    </form>
  </Dialog>
}

export function AvailabilityForm({ date, minutes, hasOverride, onClose, onSaved }: {
  date: string; minutes: number; hasOverride: boolean; onClose: () => void; onSaved: () => void
}) {
  const { dispatch, blocked } = useAppData()
  const [error, setError] = useState('')
  function save(value: number | null) {
    if (dispatch({ type: 'setAvailability', date, minutes: value })) onSaved()
    else setError('Could not save availability. Check the storage message and retry.')
  }
  return <Dialog title="Daily availability" onClose={onClose}><p>{date}</p><form noValidate onSubmit={(event) => {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const raw = String(fields.get('minutes'))
    const parsed = availabilitySchema.safeParse(raw.trim() ? Number(raw) : NaN)
    if (!parsed.success) { setError('Enter 0–1440 whole minutes.'); return }
    save(parsed.data)
  }}><Field id="availability" label="Available study minutes" error={error}><input id="availability" name="minutes" type="number" min="0" max="1440" step="1" defaultValue={minutes} required aria-invalid={!!error} aria-describedby="availability-help" /></Field>
    <div className="actions"><Button type="submit" disabled={blocked}>Save availability</Button>{hasOverride && <Button variant="secondary" disabled={blocked} onClick={() => save(null)}>Use default availability</Button>}</div>
  </form></Dialog>
}
