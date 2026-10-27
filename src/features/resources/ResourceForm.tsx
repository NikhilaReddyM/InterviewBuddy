import { useState } from 'react'
import type { FormEvent } from 'react'
import { z } from 'zod'
import { PREPARATION_AREAS, RESOURCE_SOURCES, RESOURCE_STATUSES, resourceSchema } from '../../types/models'
import type { Resource } from '../../types/models'
import { useAppData } from '../../app/dataContext'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { Button } from '../../components/Button'

const formSchema = resourceSchema.omit({ id: true, createdAt: true, updatedAt: true })

export function ResourceForm({ resource, onClose, onSaved }: {
  resource?: Resource; onClose: () => void; onSaved: () => void
}) {
  const { dispatch, blocked } = useAppData()
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saveError, setSaveError] = useState(false)
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const text = (key: string) => String(form.get(key) ?? '')
    const optional = (key: string) => text(key).trim() || undefined
    const parsed = formSchema.safeParse({
      title: text('title'), area: text('area'), source: text('source'),
      tags: [...new Set(text('tags').split(',').map((tag) => tag.trim()).filter(Boolean))],
      url: optional('url'), notes: text('notes'), status: text('status'),
      confidence: text('confidence') ? Number(text('confidence')) : undefined,
      nextRevisionDate: optional('nextRevisionDate'),
    })
    if (!parsed.success) {
      setErrors(Object.fromEntries(Object.entries(z.flattenError(parsed.error).fieldErrors).map(([key, messages]) => [key, messages?.[0] ?? 'Invalid value'])))
      return
    }
    const success = resource
      ? dispatch({ type: 'updateResource', id: resource.id, input: parsed.data })
      : dispatch({ type: 'addResource', input: parsed.data })
    if (success) onSaved()
    else setSaveError(true)
  }
  return <Dialog title={resource ? 'Edit resource' : 'Add resource'} onClose={onClose}>
    <form noValidate onSubmit={submit}>
      <Field id="resource-title" label="Title" error={errors.title}><input id="resource-title" name="title" defaultValue={resource?.title ?? ''} required aria-invalid={!!errors.title} aria-describedby="resource-title-help" /></Field>
      <Field id="resource-area" label="Preparation area"><select id="resource-area" name="area" defaultValue={resource?.area ?? 'Coding'}>{PREPARATION_AREAS.map((value) => <option key={value}>{value}</option>)}</select></Field>
      <Field id="resource-tags" label="Topic tags" hint="Separate tags with commas."><input id="resource-tags" name="tags" defaultValue={resource?.tags.join(', ') ?? ''} aria-describedby="resource-tags-help" /></Field>
      <Field id="resource-source" label="Source"><select id="resource-source" name="source" defaultValue={resource?.source ?? 'Other'}>{RESOURCE_SOURCES.map((value) => <option key={value}>{value}</option>)}</select></Field>
      <Field id="library-url" label="URL (optional)" error={errors.url}><input id="library-url" name="url" type="url" defaultValue={resource?.url ?? ''} placeholder="https://…" aria-invalid={!!errors.url} aria-describedby="library-url-help" /></Field>
      <Field id="resource-notes" label="Notes or solution text"><textarea id="resource-notes" name="notes" rows={7} defaultValue={resource?.notes ?? ''} /></Field>
      <Field id="resource-status" label="Status"><select id="resource-status" name="status" defaultValue={resource?.status ?? 'Not Started'}>{RESOURCE_STATUSES.map((value) => <option key={value}>{value}</option>)}</select></Field>
      <Field id="resource-confidence" label="Confidence" error={errors.confidence}><select id="resource-confidence" name="confidence" defaultValue={resource?.confidence ?? ''}><option value="">Not rated</option>{[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} / 5</option>)}</select></Field>
      <Field id="revision-date" label="Next revision date (optional)" error={errors.nextRevisionDate}><input id="revision-date" name="nextRevisionDate" type="date" defaultValue={resource?.nextRevisionDate ?? ''} aria-invalid={!!errors.nextRevisionDate} aria-describedby="revision-date-help" /></Field>
      {saveError && <p role="alert">Could not save. Your entries are still here. Check the storage message and retry.</p>}
      <Button type="submit" disabled={blocked}>Save resource</Button>
    </form>
  </Dialog>
}
