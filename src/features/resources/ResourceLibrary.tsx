import { useState } from 'react'
import { BookOpen } from 'lucide-react'
import { useAppData } from '../../app/dataContext'
import { PREPARATION_AREAS, RESOURCE_SOURCES, RESOURCE_STATUSES } from '../../types/models'
import { Button } from '../../components/Button'
import { Field } from '../../components/Field'
import { EmptyState } from '../../components/EmptyState'
import { ConfirmDialog } from '../../components/Dialog'
import { SessionForm } from '../planner/PlannerForms'
import { calendarDate, localDate } from '../../utils/dates'
import { ResourceForm } from './ResourceForm'
import { emptyFilters, filterResources } from './filterResources'
import type { ResourceFilters } from './filterResources'
import './resources.css'
import { LocalDocuments } from '../documents/LocalDocuments'

type Editor = { type: 'add' } | { type: 'edit' | 'delete' | 'schedule'; id: string }
export function ResourceLibrary() {
  const { data, blocked, dispatch } = useAppData()
  const [filters, setFilters] = useState<ResourceFilters>({ ...emptyFilters })
  const [editor, setEditor] = useState<Editor | null>(null)
  const [notice, setNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const [today] = useState(() => calendarDate(new Date()))
  const results = filterResources(data.resources, filters, today)
  const selected = editor && 'id' in editor ? data.resources.find((item) => item.id === editor.id) : undefined
  function filter<K extends keyof ResourceFilters>(key: K, value: ResourceFilters[K]) { setFilters((current) => ({ ...current, [key]: value })) }
  function saved(message: string) { setEditor(null); setNotice(message); setActionError('') }
  function open(next: Editor) { setEditor(next); setActionError('') }
  return <div className="resource-library">
    <LocalDocuments />
    <div className="library-toolbar"><p>Save your own notes and links. Revisit them when you’re ready.</p><Button disabled={blocked} onClick={() => open({ type: 'add' })}>Add resource</Button></div>
    <section className="card library-filters" aria-label="Resource filters">
      <Field id="resource-search" label="Search resources"><input id="resource-search" type="search" placeholder="Title, tags, or notes" value={filters.search} onChange={(event) => filter('search', event.target.value)} /></Field>
      <Field id="filter-area" label="Filter by area"><select id="filter-area" value={filters.area} onChange={(event) => filter('area', event.target.value)}><option value="">All areas</option>{PREPARATION_AREAS.map((value) => <option key={value}>{value}</option>)}</select></Field>
      <Field id="filter-source" label="Filter by source"><select id="filter-source" value={filters.source} onChange={(event) => filter('source', event.target.value)}><option value="">All sources</option>{RESOURCE_SOURCES.map((value) => <option key={value}>{value}</option>)}</select></Field>
      <Field id="filter-status" label="Filter by status"><select id="filter-status" value={filters.status} onChange={(event) => filter('status', event.target.value)}><option value="">All statuses</option>{RESOURCE_STATUSES.map((value) => <option key={value}>{value}</option>)}</select></Field>
      <Field id="filter-revision" label="Filter by revision"><select id="filter-revision" value={filters.revision} onChange={(event) => filter('revision', event.target.value as ResourceFilters['revision'])}><option value="all">All revision dates</option><option value="due">Due today or overdue</option><option value="upcoming">Future revisions</option><option value="unscheduled">No revision date</option></select></Field>
      <Field id="resource-sort" label="Sort resources"><select id="resource-sort" value={filters.sort} onChange={(event) => filter('sort', event.target.value as ResourceFilters['sort'])}><option value="updated">Recently updated</option><option value="title">Title A–Z</option><option value="revision">Next revision first</option></select></Field>
      <Button variant="secondary" onClick={() => setFilters({ ...emptyFilters })}>Clear filters</Button>
    </section>
    <p className="library-result-count" aria-live="polite">{results.length} of {data.resources.length} resources</p>
    <p role="status" className="library-notice">{notice}</p>
    {data.resources.length === 0 ? <section className="card"><EmptyState icon={<BookOpen size={28} />} title="Your library starts here" action={<Button disabled={blocked} onClick={() => open({ type: 'add' })}>Save your first resource</Button>}>Add a useful link, your solution notes, or a topic you want to revisit. Content stays exactly as you enter it.</EmptyState></section> : results.length === 0 ? <section className="card"><EmptyState title="No matching resources" action={<Button variant="secondary" onClick={() => setFilters({ ...emptyFilters })}>Reset search and filters</Button>}>Try a different search or broaden your filters.</EmptyState></section> : <div className="resource-grid">{results.map((resource) => <article className="card resource-card" aria-label={resource.title} key={resource.id}>
      <div className="resource-heading"><h2>{resource.title}</h2><span className="pill">{resource.status}</span></div>
      <p className="resource-meta">{resource.area} · {resource.source}</p>
      {resource.tags.length > 0 && <ul className="resource-tags" aria-label="Topic tags">{resource.tags.map((tag) => <li key={tag}>{tag}</li>)}</ul>}
      <p className="resource-meta">Confidence: {resource.confidence ? `${resource.confidence} / 5` : 'Not rated'}</p>
      <p className={resource.nextRevisionDate && resource.nextRevisionDate <= today ? 'revision-due' : 'resource-meta'}>{resource.nextRevisionDate ? `${resource.nextRevisionDate <= today ? 'Revision due' : 'Next revision'}: ${localDate(resource.nextRevisionDate).toLocaleDateString()}` : 'No revision date set'}</p>
      {resource.url && <a href={resource.url} target="_blank" rel="noopener noreferrer">Open resource ↗</a>}
      {resource.notes ? <details className="resource-notes"><summary>Read notes / solution</summary><pre>{resource.notes}</pre></details> : <p className="resource-meta">No notes yet.</p>}
      <div className="actions"><Button disabled={blocked} onClick={() => open({ type: 'schedule', id: resource.id })}>Schedule session</Button><Button variant="secondary" disabled={blocked} onClick={() => open({ type: 'edit', id: resource.id })}>Edit resource</Button><Button variant="danger" disabled={blocked} onClick={() => open({ type: 'delete', id: resource.id })}>Delete resource</Button></div>
    </article>)}</div>}
    {editor?.type === 'add' && <ResourceForm onClose={() => setEditor(null)} onSaved={() => saved('Resource saved. If it is hidden, clear your filters to see it.')} />}
    {editor?.type === 'edit' && selected && <ResourceForm resource={selected} onClose={() => setEditor(null)} onSaved={() => saved('Resource updated.')} />}
    {editor?.type === 'schedule' && selected && <SessionForm date={today} initial={{ topic: selected.title, area: selected.area, resourceUrl: selected.url, resourceId: selected.id }} onClose={() => setEditor(null)} onSaved={(date) => saved(`Session scheduled for ${date}. Find it in the Weekly Planner.`)} />}
    {editor?.type === 'delete' && selected && <ConfirmDialog title="Delete resource?" confirmLabel="Delete permanently" onClose={() => setEditor(null)} onConfirm={() => {
      if (dispatch({ type: 'deleteResource', id: selected.id })) saved('Resource deleted. Existing study sessions were preserved.')
      else setActionError('Could not delete. Check the storage message and retry.')
    }}><p>Delete “{selected.title}” and its notes? This cannot be undone. Existing sessions will keep their topic and resource link.</p>{actionError && <p role="alert">{actionError}</p>}</ConfirmDialog>}
  </div>
}
