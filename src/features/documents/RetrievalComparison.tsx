import { useState } from 'react'
import { Button } from '../../components/Button'

type Document = { id: string; filename: string; page_count: number }
type Hit = { id: string; text: string; score: number; metadata: { document_id: string; filename: string; pages: number[]; review_status: string } }
type Run = { method: string; elapsed_ms: number; results: Hit[] }

export function RetrievalComparison({ documents }: { documents: Document[] }) {
  const [opened, setOpened] = useState(false)
  const [ids, setIds] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [runs, setRuns] = useState<Run[]>([])
  async function compare() {
    setBusy(true); setError(''); setRuns([])
    try {
      // Sequential calls share the same model lock and corpus selection.
      const results = []
      for (const method of ['dense', 'keyword', 'hybrid']) {
        const response = await fetch('/api/retrieval/search', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' },
          body: JSON.stringify({ document_ids: ids, query, method, top_k: 5, group_pages: true }) })
        if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Restart the document backend and try again.')
        const result = await response.json()
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Search failed. Check your selection.')
        results.push(result as Run)
      }
      setRuns(results)
    } catch (error) { setError((error as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="pdf-comparison" aria-label="Retrieval comparison">
    <Button variant="secondary" disabled={busy} aria-expanded={opened} onClick={() => setOpened(!opened)}>{opened ? 'Close comparison' : 'Compare search methods'}</Button>
    {opened && <>
      <h3>Compare retrieval</h3>
      <p className="pdf-muted">Select PDFs with current indexes. Compare the same question across semantic, keyword, and hybrid search.</p>
      <fieldset disabled={busy}><legend>Search corpus</legend>{documents.filter(d => d.page_count > 0).map(d => <label className="pdf-checkbox" key={d.id}>
        <input type="checkbox" checked={ids.includes(d.id)} onChange={event => { setIds(current => event.target.checked ? [...current, d.id] : current.filter(id => id !== d.id)); setRuns([]) }} />{d.filename}
      </label>)}</fieldset>
      <form className="pdf-search-form" onSubmit={event => { event.preventDefault(); compare() }}>
        <label>Comparison question<input value={query} maxLength={4000} onChange={event => { setQuery(event.target.value); setRuns([]) }} /></label>
        <Button type="submit" disabled={busy || !ids.length || !query.trim()}>{busy ? 'Comparing…' : 'Compare all three'}</Button>
      </form>
      {error && <p className="pdf-error" role="alert">{error}</p>}
      {!!runs.length && <p className="pdf-muted">Evidence unverified. Similarity, BM25, and fusion scores use different scales; inspect the source pages to judge relevance.</p>}
      <div className="pdf-comparison-grid">{runs.map(run => <section key={run.method}>
        <h4>{run.method === 'dense' ? 'Semantic' : run.method === 'keyword' ? 'Keyword' : 'Hybrid'}</h4>
        <p className="pdf-muted">{run.elapsed_ms.toFixed(1)} ms ranking time · {run.results.length} results</p>
        {!run.results.length && <p>No matching passages. This does not establish that the full PDFs lack an answer.</p>}
        {run.results.map((hit, i) => <article className="pdf-search-result" key={hit.id}>
          <p>#{i + 1} · {hit.metadata.filename} · Page {hit.metadata.pages.join(', ')} · {hit.metadata.review_status}</p>
          <a href={`/api/documents/${hit.metadata.document_id}/original#page=${hit.metadata.pages[0]}`} target="_blank" rel="noreferrer">Open supporting page</a>
          <details><summary>Read passage</summary><pre>{hit.text}</pre></details>
        </article>)}
      </section>)}</div>
    </>}
  </section>
}
