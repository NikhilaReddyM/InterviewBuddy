import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'

type Chunk = { id?: string; text: string; metadata: { pages: number[]; token_count: number; review_status: string; method: string; experimental: boolean; content_type: string; split_page: boolean }; score?: number }
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

export function DocumentIndex({ documentId, pageCount, sourceVersion }: { documentId: string; pageCount: number; sourceVersion: string }) {
  const [opened, setOpened] = useState(false)
  const [start, setStart] = useState(1)
  const [end, setEnd] = useState(Math.min(10, pageCount))
  const [experimental, setExperimental] = useState(false)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [results, setResults] = useState<Chunk[]>([])
  const [searched, setSearched] = useState(false)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [limit, setLimit] = useState(10)
  useEffect(() => {
    if (!opened) return
    const controller = new AbortController()
    api<Status>(`/api/index/${documentId}`, undefined, controller.signal).then(result => {
      if (!controller.signal.aborted) { setStatus(result); setPlan(null); setResults([]); setSearched(false) }
    }).catch(error => { if (!controller.signal.aborted) setError(error.message) })
    return () => controller.abort()
  }, [opened, documentId, sourceVersion])
  const selection = { document_id: documentId, start_page: start, end_page: end, include_unreviewed: experimental }
  function changed() { setPlan(null); setNotice(''); setLimit(10) }
  async function run(action: 'preview' | 'build' | 'search') {
    setBusy(true); setError(''); setNotice('')
    try {
      if (action === 'preview') {
        setPlan(await api<Plan>('/api/index/preview', selection)); setLimit(10)
      } else if (action === 'build') {
        const result = await api<{ chunk_count: number; embedded: number; reused: number }>('/api/index/build', selection)
        setStatus(await api<Status>(`/api/index/${documentId}`)); setPlan(null); setResults([]); setSearched(false)
        setNotice(`Index saved: ${result.chunk_count} chunks; ${result.embedded} new embeddings, ${result.reused} reused.`)
      } else {
        const result = await api<{ results: Chunk[] }>(`/api/index/${documentId}/search`, { query, top_k: 5 })
        setResults(result.results); setSearched(true)
      }
    } catch (error) { setError((error as Error).message) }
    finally { setBusy(false) }
  }
  const chunks = plan?.chunks ?? status?.chunks ?? []
  return <section className="pdf-index" aria-label="Document indexing">
    <h4>Chunking and indexing</h4>
    <Button variant="secondary" disabled={busy} onClick={() => setOpened(!opened)}>{opened ? 'Close indexing' : 'Index this PDF'}</Button>
    {opened && <>
      <p>Select saved pages to turn into searchable passages. Unreviewed content is optional; you do not have to clear the review queue.</p>
      <p>Embeddings run on this machine using BGE-small. The first run downloads model files. No PDF text is uploaded.</p>
      {error && <p role="alert">{error}</p>}
      <p role="status">{busy ? 'Processing locally… Keep this panel open until it finishes.' : notice}</p>
      <fieldset disabled={busy}>
        <legend>Pages to index</legend>
        <label>First PDF page <input type="number" min={1} max={pageCount} value={start} onChange={event => { setStart(Number(event.target.value)); changed() }} /></label>
        <label>Last PDF page <input type="number" min={start} max={pageCount} value={end} onChange={event => { setEnd(Number(event.target.value)); changed() }} /></label>
        <label><input type="checkbox" checked={experimental} onChange={event => { setExperimental(event.target.checked); changed() }} /> Include unreviewed pages experimentally</label>
      </fieldset>
      <p>Confirmed blank pages, manually flagged pages, empty text, and extraction failures are excluded. Builds use saved corrections, not unsaved editor text.</p>
      <div className="actions">
        <Button disabled={busy || start < 1 || end < start || end > pageCount} variant="secondary" onClick={() => run('preview')}>Preview chunks</Button>
        <Button disabled={busy || !plan?.chunks.length} onClick={() => run('build')}>Build / replace index</Button>
      </div>
      <p>Each PDF has one active index. Building replaces its previous page selection after successful embedding.</p>
      {plan && <>
        <p>{plan.included_pages.length} pages included · {plan.skipped_pages.length} skipped · {plan.chunks.length} chunks</p>
        {!!plan.skipped_pages.length && <details><summary>Skipped pages and reasons</summary><ul>{plan.skipped_pages.map(p => <li key={p.page}>PDF page {p.page}: {p.reason}</li>)}</ul></details>}
      </>}
      {status && <p>Saved index: {status.state === 'not_indexed' ? 'Not built' : status.state === 'stale' ? 'Stale — source pages changed; rebuild before searching' : `${status.chunks.length} chunks ready`}{status.built_at ? ` · Built ${new Date(status.built_at).toLocaleString()}` : ''}</p>}
      {status?.selection && <p>Saved selection: PDF pages {status.selection.start_page}–{status.selection.end_page} · {status.included} included · {status.skipped?.length ?? 0} skipped · {status.selection.include_unreviewed ? 'Experimental unreviewed inclusion enabled' : 'Reviewed pages only'}</p>}
      {(plan?.config ?? status?.config) && <p>Model: {(plan?.config ?? status?.config)?.model} · Up to {(plan?.config ?? status?.config)?.max_tokens} model tokens per chunk · {(plan?.config ?? status?.config)?.overlap_tokens} token overlap within split pages</p>}
      {chunks.slice(0, limit).map((chunk, i) => <details key={chunk.id ?? i}>
        <summary>Chunk {i + 1} · PDF page {chunk.metadata.pages.join(', ')} · {chunk.metadata.token_count} tokens · {chunk.metadata.review_status}</summary>
        <p>{chunk.metadata.experimental ? 'Experimental, unreviewed text.' : 'Reviewed source text.'} Section type: {chunk.metadata.content_type}.{chunk.metadata.split_page ? ' Long page split; check code continuity.' : ''}</p>
        <a href={`/api/documents/${documentId}/original#page=${chunk.metadata.pages[0]}`} target="_blank" rel="noreferrer">Open source page</a>
        <pre>{chunk.text}</pre>
      </details>)}
      {chunks.length > limit && <Button variant="secondary" onClick={() => setLimit(limit + 10)}>Show more chunks</Button>}
      <form onSubmit={event => { event.preventDefault(); run('search') }}>
        <label>Test similarity search <input value={query} maxLength={4000} onChange={event => setQuery(event.target.value)} placeholder="When should I use binary search?" /></label>
        <Button type="submit" disabled={busy || status?.state !== 'ready' || !query.trim()}>Search indexed passages</Button>
      </form>
      <p>This diagnostic returns passages, not AI answers. Similarity scores are not confidence or proof of relevance. Unknown sections may contain solutions.</p>
      {searched && !results.length && <p>No passages found.</p>}
      {results.map((chunk, i) => <article key={i}>
        <p>Result {i + 1} · PDF page {chunk.metadata.pages.join(', ')} · Similarity {chunk.score?.toFixed(3)} · {chunk.metadata.review_status}</p>
        <a href={`/api/documents/${documentId}/original#page=${chunk.metadata.pages[0]}`} target="_blank" rel="noreferrer">Open supporting page</a>
        <pre>{chunk.text}</pre>
      </article>)}
    </>}
  </section>
}
