import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { z } from 'zod'
import { designAttemptSchema } from '../../types/models'
import type { DesignAttempt } from '../../types/models'
import type { DesignAttemptInput } from '../../app/dataActions'
import { createEmptyChecklist } from '../../types/defaults'
import { useAppData } from '../../app/dataContext'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { DESIGN_CHECKLIST, DESIGN_SECTIONS } from './designFields'

const inputSchema = designAttemptSchema.omit({ id: true, createdAt: true, updatedAt: true })
function initialValues(attempt?: DesignAttempt): DesignAttemptInput {
  return {
    title: attempt?.title ?? '',
    requirementsAndAssumptions: attempt?.requirementsAndAssumptions ?? '',
    scaleEstimates: attempt?.scaleEstimates ?? '',
    apisAndDataModel: attempt?.apisAndDataModel ?? '',
    architectureNotes: attempt?.architectureNotes ?? '',
    tradeoffsAndFailureScenarios: attempt?.tradeoffsAndFailureScenarios ?? '',
    missedAndNextSteps: attempt?.missedAndNextSteps ?? '',
    checklist: attempt ? { ...attempt.checklist } : createEmptyChecklist(),
    confidence: attempt?.confidence,
  }
}

export function DesignAttemptForm({ attempt, onClose, onSaved }: {
  attempt?: DesignAttempt; onClose: () => void; onSaved: () => void
}) {
  const { dispatch, blocked } = useAppData()
  const [initial] = useState(() => initialValues(attempt))
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saveError, setSaveError] = useState(false)
  const [discard, setDiscard] = useState(false)
  const dirty = JSON.stringify(values) !== JSON.stringify(initial)
  useEffect(() => {
    if (!dirty) return
    function beforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsed = inputSchema.safeParse(values)
    if (!parsed.success) {
      setErrors(Object.fromEntries(Object.entries(z.flattenError(parsed.error).fieldErrors).map(([key, messages]) => [key, messages?.[0] ?? 'Invalid value'])))
      return
    }
    const success = attempt
      ? dispatch({ type: 'updateDesignAttempt', id: attempt.id, input: parsed.data })
      : dispatch({ type: 'addDesignAttempt', input: parsed.data })
    if (success) onSaved()
    else setSaveError(true)
  }
  return <Dialog title={discard ? 'Discard unsaved changes?' : attempt ? 'Edit practice attempt' : 'New practice attempt'}
    closeLabel={discard ? 'Keep editing' : 'Cancel'} onClose={() => {
      if (discard) setDiscard(false)
      else if (dirty) setDiscard(true)
      else onClose()
    }}>
    {discard ? <><p>Your changes have not been saved. Discard them and return to the lab?</p><Button variant="danger" onClick={onClose}>Discard changes</Button></> :
      <form className="design-form" noValidate onSubmit={submit}>
        <p className="design-muted">Self-assessment only. Save your reasoning and use the checklist to spot gaps.</p>
        <Field id="design-title" label="Problem title" error={errors.title}><input id="design-title" required value={values.title} onChange={(event) => setValues({ ...values, title: event.target.value })} aria-invalid={!!errors.title} aria-describedby="design-title-help" /></Field>
        {DESIGN_SECTIONS.map(({ key, label, hint }) => <Field key={key} id={`design-${key}`} label={label} hint={hint} error={errors[key]}><textarea id={`design-${key}`} rows={4} value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} aria-describedby={`design-${key}-help`} /></Field>)}
        <fieldset className="design-checklist"><legend>Design review checklist</legend><p className="design-muted">Check each concern once you have considered it in your design.</p>{DESIGN_CHECKLIST.map(({ key, label, hint }) => <div key={key}><label><input type="checkbox" checked={values.checklist[key]} onChange={(event) => setValues({ ...values, checklist: { ...values.checklist, [key]: event.target.checked } })} aria-describedby={`check-${key}`} /><span>{label}</span></label><p id={`check-${key}`}>{hint}</p></div>)}</fieldset>
        <Field id="design-confidence" label="Self-rated confidence" error={errors.confidence}><select id="design-confidence" value={values.confidence ?? ''} onChange={(event) => setValues({ ...values, confidence: event.target.value ? Number(event.target.value) : undefined })}><option value="">Not rated</option>{[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} / 5</option>)}</select></Field>
        {saveError && <p role="alert">Could not save. Your writing is still here. Check the storage message and retry.</p>}
        <Button type="submit" disabled={blocked}>Save attempt</Button>
      </form>}
  </Dialog>
}
