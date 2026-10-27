import { useState } from 'react'
import { FlaskConical } from 'lucide-react'
import { useAppData } from '../../app/dataContext'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { ConfirmDialog } from '../../components/Dialog'
import { DesignAttemptForm } from './DesignAttemptForm'
import { DESIGN_CHECKLIST, DESIGN_SECTIONS } from './designFields'
import './design-lab.css'

type Editor = { type: 'add' } | { type: 'edit' | 'delete'; id: string }
export function SystemDesignLab() {
  const { data, dispatch, blocked } = useAppData()
  const [editor, setEditor] = useState<Editor | null>(null)
  const [notice, setNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const selected = editor && 'id' in editor ? data.designAttempts.find((attempt) => attempt.id === editor.id) : undefined
  const attempts = [...data.designAttempts].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.title.localeCompare(b.title))
  function saved(message: string) { setEditor(null); setNotice(message); setActionError('') }
  return <div className="design-lab">
    <div className="design-toolbar"><div><h2>Practice your design thinking</h2><p>Capture your approach, question your assumptions, and decide what to improve next.</p></div><Button disabled={blocked} onClick={() => setEditor({ type: 'add' })}>New attempt</Button></div>
    <div className="design-assessment-note"><FlaskConical size={20} aria-hidden="true" /><p>Self-assessment only · Checklist completion reflects what you considered, not a score for correctness.</p></div>
    <p role="status" className="design-notice">{notice}</p>
    {attempts.length === 0 ? <section className="card"><EmptyState icon={<FlaskConical size={28} />} title="Make room for your first design" action={<Button disabled={blocked} onClick={() => setEditor({ type: 'add' })}>Start your first attempt</Button>}>Choose a problem such as a URL shortener or notification service. Write down your reasoning, then review it using the checklist.</EmptyState></section> : <div className="design-attempts">{attempts.map((attempt) => <article className="card design-attempt" key={attempt.id} aria-label={attempt.title}>
      <div className="design-attempt-heading"><h2>{attempt.title}</h2><span className="pill">{Object.values(attempt.checklist).filter(Boolean).length} / 5 considered</span></div>
      <p className="design-muted">Updated {new Date(attempt.updatedAt).toLocaleString()} · Confidence: {attempt.confidence ? `${attempt.confidence} / 5` : 'Not rated'}</p>
      <ul className="design-checklist-summary" aria-label="Design checklist">{DESIGN_CHECKLIST.map(({ key, label }) => <li key={key}><span aria-hidden="true">{attempt.checklist[key] ? '✓' : '○'}</span> {label}: {attempt.checklist[key] ? 'Considered' : 'Not yet considered'}</li>)}</ul>
      <details className="design-review"><summary>Read practice notes</summary>{DESIGN_SECTIONS.map(({ key, label }) => <section key={key}><h3>{label}</h3><p className="design-text">{attempt[key] || 'No notes yet.'}</p></section>)}</details>
      <div className="actions"><Button variant="secondary" disabled={blocked} onClick={() => setEditor({ type: 'edit', id: attempt.id })}>Edit attempt</Button><Button variant="danger" disabled={blocked} onClick={() => { setActionError(''); setEditor({ type: 'delete', id: attempt.id }) }}>Delete attempt</Button></div>
    </article>)}</div>}
    {editor?.type === 'add' && <DesignAttemptForm onClose={() => setEditor(null)} onSaved={() => saved('Practice attempt saved.')} />}
    {editor?.type === 'edit' && selected && <DesignAttemptForm attempt={selected} onClose={() => setEditor(null)} onSaved={() => saved('Practice attempt updated.')} />}
    {editor?.type === 'delete' && selected && <ConfirmDialog title="Delete practice attempt?" confirmLabel="Delete permanently" onClose={() => setEditor(null)} onConfirm={() => {
      if (dispatch({ type: 'deleteDesignAttempt', id: selected.id })) saved('Practice attempt deleted.')
      else setActionError('Could not delete. Check the storage message and retry.')
    }}><p>Delete “{selected.title}” and all of its practice notes? This cannot be undone.</p>{actionError && <p role="alert">{actionError}</p>}</ConfirmDialog>}
  </div>
}
