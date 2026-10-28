import { useEffect, useRef, useState } from 'react'
import { Button } from '../../components/Button'

type Chunk = { id?: string; text: string; metadata: { pages: number[]; token_count: number; review_status: string; method: string; experimental: boolean; content_type: string; split_page: boolean }; score?: number; score_type?: string }
type Plan = { included_pages: number[]; skipped_pages: { page: number; reason: string }[]; chunks: Chunk[]; config: { model: string; max_tokens: number; overlap_tokens: number } }
type Status = { selection?: { start_page: number; end_page: number; include_unreviewed: boolean }; included?: number; skipped?: Plan['skipped_pages']; state: string; built_at?: string; config?: Plan['config']; chunks: Chunk[] }
async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal, ...(body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(body),
  }) })
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Document backend unavailable. Start or restart it and try again.')
  const result = await response.json()
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Check page range and try again.')
  return result
}

export function DocumentIndex({ documentId, pageCount, sourceVersion, embedded = false, onBusyChange }: { documentId: string; pageCount: number; sourceVersion: string; embedded?: boolean; onBusyChange?: (busy: boolean) => void }) {
  const [opened, setOpened] = useState(embedded)
  const initialized = useRef(false)
  const [refresh, setRefresh] = useState(0)
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [start, setStart] = useState(1)
  const [end, setEnd] = useState(Math.min(10, pageCount))
  const [experimental, setExperimental] = useState(false)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [results, setResults] = useState<Chunk[]>([])
  const [searched, setSearched] = useState(false)
  const [query, setQuery] = useState('')
  const [retrievalMethod, setRetrievalMethod] = useState('dense')
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [limit, setLimit] = useState(10)
  useEffect(() => {
    if (!opened) return
    const controller = new AbortController()
    // Synchronize status feedback with the backend request.
    // oxlint-disable-next-line react/set-state-in-effect
    setLoadingStatus(true)
    setError('')
    api<Status>(`/api/index/${documentId}`, undefined, controller.signal).then(result => {
      if (!controller.signal.aborted) {
        setStatus(result); setPlan(null); setResults([]); setSearched(false)
        if (!initialized.current && result.selection) {
          setStart(result.selection.start_page); setEnd(result.selection.end_page); setExperimental(result.selection.include_unreviewed)
        }
        initialized.current = true
      }
    }).catch(error => { if (!controller.signal.aborted) setError(error.message) })
      .finally(() => { if (!controller.signal.aborted) setLoadingStatus(false) })
    return () => controller.abort()
  }, [opened, documentId, sourceVersion, refresh])
  const selection = { document_id: documentId, start_page: start, end_page: end, include_unreviewed: experimental }
  function changed() { setPlan(null); setNotice(''); setLimit(10) }
  async function run(action: 'preview' | 'build' | 'search') {
    setBusy(true); onBusyChange?.(true); setError(''); setNotice('')
    try {
      if (action === 'preview') {
        setPlan(await api<Plan>('/api/index/preview', selection)); setLimit(10)
      } else if (action === 'build') {
        const result = await api<{ chunk_count: number; embedded: number; reused: number }>('/api/index/build', selection)
        setStatus(await api<Status>(`/api/index/${documentId}`)); setPlan(null); setResults([]); setSearched(false)
        setNotice(`Index saved: ${result.chunk_count} chunks; ${result.embedded} new embeddings, ${result.reused} reused.`)
      } else {
        const result = await api<{ results: Chunk[]; elapsed_ms?: number }>(`/api/index/${documentId}/search`, { query, top_k: 5, method: retrievalMethod, group_pages: true })
        setResults(result.results); setElapsed(result.elapsed_ms ?? null); setSearched(true)
      }
    } catch (error) { setError((error as Error).message) }
    finally { setBusy(false); onBusyChange?.(false) }
  }
  const chunks = plan?.chunks ?? status?.chunks ?? []
  return <section className="pdf-index" aria-label="Document indexing">
    {!embedded && <><h4>Chunking and indexing</h4>
    <Button variant="secondary" disabled={busy} onClick={() => setOpened(!opened)}>{opened ? 'Close indexing' : 'Index this PDF'}</Button></>}
    {opened && <>
      <div className="pdf-index-heading"><div><h4>Make this PDF searchable</h4><p className="pdf-muted">Choose pages, preview passages, then build your index.</p></div><span className="pdf-badge">Local processing</span></div>
      {loadingStatus && <p role="status">Checking saved index…</p>}
      {error && <div className="pdf-error" role="alert"><p>{error}</p><Button variant="secondary" disabled={busy || loadingStatus} onClick={() => setRefresh(value => value + 1)}>Refresh index status</Button></div>}
      {(busy || notice) && <p className="pdf-notice" role="status">{busy ? 'Processing locally…' : notice}</p>}
      {status && <div className={`pdf-index-status ${status.state === 'stale' ? 'pdf-index-stale' : ''}`}><strong>Saved index: {status.state === 'not_indexed' ? 'Not built' : status.state === 'stale' ? 'Stale — source pages changed; rebuild before searching' : `${status.chunks.length} chunks ready`}</strong>
      {status.selection && <p>PDF pages {status.selection.start_page}–{status.selection.end_page} · {status.included} included · {status.skipped?.length ?? 0} skipped</p>}
      {status.built_at && <small>Updated {new Date(status.built_at).toLocaleString()}</small>}</div>}
      <fieldset disabled={busy || loadingStatus} className="pdf-index-selection">
        <legend>Pages to index</legend>
        <div className="pdf-page-range"><label>First PDF page <input type="number" min={1} max={pageCount} value={start} onChange={event => { setStart(Number(event.target.value)); changed() }} /></label>
        <label>Last PDF page <input type="number" min={start} max={pageCount} value={end} onChange={event => { setEnd(Number(event.target.value)); changed() }} /></label></div>
        <label className="pdf-checkbox"><input type="checkbox" checked={experimental} onChange={event => { setExperimental(event.target.checked); changed() }} /> Include unreviewed pages experimentally</label>
      </fieldset>

      <div className="actions">
        <Button disabled={busy || loadingStatus || start < 1 || end < start || end > pageCount} variant="secondary" onClick={() => run('preview')}>Preview chunks</Button>
        <Button disabled={busy || loadingStatus || !plan?.chunks.length} onClick={() => run('build')}>Build / replace index</Button>
      </div>
      <p className="pdf-muted pdf-help">Preview first to enable Build. A successful build replaces this PDF’s saved page selection.</p>
      {plan && <>
        <p>{plan.included_pages.length} pages included · {plan.skipped_pages.length} skipped · {plan.chunks.length} chunks</p>
        {!!plan.skipped_pages.length && <details><summary>Skipped pages and reasons</summary><ul>{plan.skipped_pages.map(p => <li key={p.page}>PDF page {p.page}: {p.reason}</li>)}</ul></details>}
      </>}
      <details className="pdf-technical"><summary>Index settings & inclusion rules</summary>
      <p>Uses saved text. Blank, manually flagged, empty, and failed-extraction pages are skipped. Unreviewed pages are included only when selected above.</p>
      <p>Embeddings run locally using BGE-small; the first run downloads model files. No PDF text is uploaded.</p>
      {(plan?.config ?? status?.config) && <p>Model: {(plan?.config ?? status?.config)?.model} · Maximum {(plan?.config ?? status?.config)?.max_tokens} tokens · {(plan?.config ?? status?.config)?.overlap_tokens} token overlap</p>}
      </details>
      <details className="pdf-chunk-list"><summary>{plan ? 'Preview' : 'Browse'} passages ({chunks.length})</summary>
      {chunks.slice(0, limit).map((chunk, i) => <details key={chunk.id ?? i}>
        <summary>Chunk {i + 1} · PDF page {chunk.metadata.pages.join(', ')} · {chunk.metadata.token_count} tokens · {chunk.metadata.review_status}</summary>
        <p>{chunk.metadata.experimental ? 'Experimental, unreviewed text.' : 'Reviewed source text.'} Section type: {chunk.metadata.content_type}.{chunk.metadata.split_page ? ' Long page split; check code continuity.' : ''}</p>
        <a href={`/api/documents/${documentId}/original#page=${chunk.metadata.pages[0]}`} target="_blank" rel="noreferrer">Open source page</a>
        <pre>{chunk.text}</pre>
      </details>)}
      {chunks.length > limit && <Button variant="secondary" onClick={() => setLimit(limit + 10)}>Show more chunks</Button>}
      </details>
      <label className="pdf-method-label">Retrieval method <select value={retrievalMethod} disabled={busy} onChange={event => { setRetrievalMethod(event.target.value); setResults([]); setSearched(false) }}>
        <option value="dense">Semantic (dense)</option><option value="keyword">Keyword (BM25)</option><option value="hybrid">Hybrid (rank fusion)</option>
      </select></label>
      <form className="pdf-search-form" onSubmit={event => { event.preventDefault(); run('search') }}>
        <label>Test similarity search <input value={query} maxLength={4000} onChange={event => setQuery(event.target.value)} placeholder="When should I use binary search?" /></label>
        <Button type="submit" disabled={busy || loadingStatus || status?.state !== 'ready' || !query.trim()}>Search indexed passages</Button>
      </form>
      <p className="pdf-muted pdf-help">Returns source passages, which may include solutions. AI answers come later.</p>
      {searched && <p className="pdf-muted">Evidence unverified · {elapsed !== null ? `${elapsed.toFixed(1)} ms ranking time` : 'Inspect source pages'}</p>}
      {searched && !results.length && <p>No passages found.</p>}
      {results.map((chunk, i) => <article className="pdf-search-result" key={i}>
        <p>Result {i + 1} · PDF page {chunk.metadata.pages.join(', ')} · {chunk.score_type === 'bm25_plus' ? 'BM25' : chunk.score_type === 'reciprocal_rank_fusion' ? 'Fusion' : 'Similarity'} {chunk.score?.toFixed(3)} · {chunk.metadata.review_status}</p>
        <a href={`/api/documents/${documentId}/original#page=${chunk.metadata.pages[0]}`} target="_blank" rel="noreferrer">Open supporting page</a>
        <pre>{chunk.text}</pre>
      </article>)}
    </>}
  </section>
}
