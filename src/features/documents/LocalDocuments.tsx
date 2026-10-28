import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import './documents.css'
import { DocumentIndex } from './DocumentIndex'

type Summary = { id: string; filename: string; page_count: number; status: string; unreviewed: number; needs_attention?: number; spot_check?: number; error: string | null }
type PageSummary = { number: number; review_status: string; needs_attention: boolean; attention_reasons: string[]; priority: string }
type PageFilter = 'all' | 'attention' | 'spot_check' | 'reviewed'
type Page = { number: number; text: string; direct_text: string; ocr_text: string; method: 'direct' | 'ocr'; issues: string[]; review_status: string; revision: number; attention_reasons?: string[]; page_index?: PageSummary[] }
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
    throw new Error(response.status === 409 ? 'This page changed. Close and reopen the library before saving.' : 'Local document request failed. Check that the backend is running; see the local PDF library setup instructions.')
  }
  return response.json()
}

export function LocalDocuments() {
  const [opened, setOpened] = useState(false)
  const [documents, setDocuments] = useState<Summary[]>([])
  const [selected, setSelected] = useState<Summary | null>(null)
  const [number, setNumber] = useState(1)
  const [filter, setFilter] = useState<PageFilter>('all')
  const [page, setPage] = useState<Page | null>(null)
  const [text, setText] = useState('')
  const [method, setMethod] = useState<'direct' | 'ocr'>('direct')
  const [status, setStatus] = useState('unreviewed')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  const index = page?.page_index ?? Array.from({ length: selected?.page_count ?? 0 }, (_, i) => ({ number: i + 1, review_status: 'unreviewed', needs_attention: false, attention_reasons: [], priority: 'spot_check' }))
  const matches = index.filter(p => filter === 'all' || (filter === 'attention' ? p.needs_attention : filter === 'spot_check' ? p.priority === 'spot_check' : p.priority === 'reviewed'))
  const previous = matches.filter(p => p.number < number).at(-1)?.number
  const next = matches.find(p => p.number > number)?.number
  const currentMatches = matches.some(p => p.number === number)
  const dirty = !!page && (text !== page.text || method !== page.method || status !== page.review_status)
  function mayLeave() { return !dirty || window.confirm('Discard unsaved page corrections?') }
  useEffect(() => {
    if (!dirty) return
    const handler = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const navigate = (event: Event) => {
      if (!window.confirm('Discard unsaved page corrections?')) event.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    window.addEventListener('interviewbuddy:before-navigate', navigate)
    return () => {
      window.removeEventListener('beforeunload', handler)
      window.removeEventListener('interviewbuddy:before-navigate', navigate)
    }
  }, [dirty])
  useEffect(() => {
    if (!opened) return
    const controller = new AbortController()
    // Synchronize loading state with the external document request.
    // oxlint-disable-next-line react/set-state-in-effect
    setBusy(true); setError(''); setNotice(''); setPage(null)
    const url = selected ? `/api/documents/${selected.id}/pages/${number}` : '/api/documents'
    request<Summary[] | Page>(url, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return
      if (Array.isArray(result)) setDocuments(result)
      else { setPage(result); setText(result.text); setMethod(result.method); setStatus(result.review_status) }
    }).catch(error => { if (!controller.signal.aborted) setError(error.message) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [opened, selected, number, refresh])
  async function save() {
    if (!page || !selected) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await request<Page>(`/api/documents/${selected.id}/pages/${number}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' },
        body: JSON.stringify({ text, method, review_status: status, revision: page.revision }),
      })
      setPage(result); setText(result.text); setNotice('Page corrections and review status saved locally.')
    } catch (error) { setError((error as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="card pdf-library" aria-label="Local PDF library">
    <h2>Local PDF library</h2>
    <p>Imported PDFs and corrections live on this machine, separately from browser backups. Select a PDF to review pages or build a local search index.</p>
    <Button variant="secondary" disabled={busy} onClick={() => { if (mayLeave()) { setOpened(!opened); setSelected(null); setPage(null) } }}>{opened ? 'Close PDF library' : 'Open PDF library'}</Button>
    {opened && <>
      {busy && <p role="status">Loading or saving…</p>}
      {error && <p role="alert">{error}</p>}
      <p role="status">{notice}</p>
      {!selected && <>
        <p>Choose a PDF, then use Needs attention to focus your review. Use Refresh PDFs after importing new files.</p>
        <Button variant="secondary" disabled={busy} onClick={() => setRefresh(refresh + 1)}>Refresh PDFs</Button>
        {!busy && !error && !documents.length && <p>No PDFs imported yet.</p>}
        <ul>{documents.map(doc => <li key={doc.id}>
          <Button variant="secondary" disabled={busy || !doc.page_count} onClick={() => { setSelected(doc); setNumber(1); setFilter('all') }}>{doc.filename}</Button>
          <p>{doc.page_count} pages · {doc.status} · {doc.needs_attention ?? 0} need attention · {doc.spot_check ?? 0} for spot-checking</p>
          {doc.error && <p>{doc.error}</p>}
        </li>)}</ul>
      </>}
      {selected && <>
        <h3>{selected.filename}</h3>
        <DocumentIndex key={selected.id} documentId={selected.id} pageCount={selected.page_count} sourceVersion={`${number}-${page?.revision ?? 0}`} />
        <p>You do not need to review every page. Focus on flagged pages and spot-check the rest. These signals can miss errors; they do not certify accuracy.</p>
        <label>Review filter <select disabled={busy} value={filter} onChange={event => {
          if (!mayLeave()) return
          const value = event.target.value as PageFilter
          setFilter(value)
          const first = index.find(p => value === 'all' || (value === 'attention' ? p.needs_attention : value === 'spot_check' ? p.priority === 'spot_check' : p.priority === 'reviewed'))
          if (first) setNumber(first.number)
        }}>
          <option value="all">All pages ({index.length})</option>
          <option value="attention">Needs attention ({index.filter(p => p.needs_attention).length})</option>
          <option value="spot_check">Spot-check candidates ({index.filter(p => p.priority === 'spot_check').length})</option>
          <option value="reviewed">Reviewed / confirmed blank ({index.filter(p => p.priority === 'reviewed').length})</option>
        </select></label>
        {!matches.length && <p>No pages match this filter. Choose All pages to browse the document.</p>}
        {!currentMatches && <p>The current page is outside this filter. Your saved review remains visible; choose another page or change the filter.</p>}
        <div className="actions">
          <Button variant="secondary" disabled={busy} onClick={() => { if (mayLeave()) { setSelected(null); setPage(null) } }}>Back to PDFs</Button>
          <Button variant="secondary" disabled={busy || previous === undefined} onClick={() => { if (mayLeave()) setNumber(previous!) }}>Previous page</Button>
          <label>PDF page <select disabled={busy} value={number} onChange={event => { if (mayLeave()) setNumber(Number(event.target.value)) }}>
            {!currentMatches && <option value={number}>{number} (current page)</option>}
            {matches.map(p => <option key={p.number} value={p.number}>{p.number}{p.needs_attention ? ' — needs attention' : ''}</option>)}
          </select> of {selected.page_count}</label>
          <Button variant="secondary" disabled={busy || next === undefined} onClick={() => { if (mayLeave()) setNumber(next!) }}>Next page</Button>
          <a href={`/api/documents/${selected.id}/original#page=${number}`} target="_blank" rel="noreferrer">Open original PDF</a>
        </div>
        {page && <>
          <h4>Review priority</h4>
          {page.attention_reasons?.length ? <ul>{page.attention_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul> : <p>No automated attention flags. Spot-checking is still recommended.</p>}
          <details><summary>Extraction notes</summary><ul>{page.issues.map(issue => <li key={issue}>{issue}</li>)}</ul></details>
          <div className="pdf-page-grid">
            <a href={`/api/documents/${selected.id}/pages/${number}/image`} target="_blank" rel="noreferrer"><img src={`/api/documents/${selected.id}/pages/${number}/image`} alt={`Original PDF page ${number} of ${selected.filename}`} /></a>
            <div>
              <label>Text source <select disabled={busy} value={method} onChange={event => {
                if (window.confirm('Replace the editor text with this raw extraction?')) {
                  const next = event.target.value as 'direct' | 'ocr'; setMethod(next); setText(page[`${next}_text`]); setStatus('unreviewed')
                }
              }}><option value="direct">Direct text</option><option value="ocr">Apple Vision OCR</option></select></label>
              <label>Reviewed text<textarea disabled={busy} value={text} onChange={event => { setText(event.target.value); setStatus('unreviewed') }} /></label>
              <label>Review status <select disabled={busy} value={status} onChange={event => setStatus(event.target.value)}>
                <option value="unreviewed">Not reviewed</option><option value="flagged">Flagged for follow-up</option><option value="reviewed">Reviewed</option><option value="confirmed_blank">Confirmed blank</option>
              </select></label>
              <p>Confirm blank only after checking the image and clearing the reviewed text. Code and diagrams require visual verification.</p>
              <Button disabled={busy || !dirty || (status === 'confirmed_blank' && !!text.trim())} onClick={save}>Save page review</Button>
              <details><summary>Raw direct extraction</summary><pre>{page.direct_text || 'No direct text.'}</pre></details>
              <details><summary>Raw OCR extraction</summary><pre>{page.ocr_text || 'No OCR text.'}</pre></details>
            </div>
          </div>
        </>}
      </>}
    </>}
  </section>
}
