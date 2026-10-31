import { useEffect, useRef, useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { Button } from '../../components/Button'

type Config = { provider: string; model: string | null; configured: boolean; documents: { filename: string }[]; corpus_error: string | null }
type Source = { source_id: string; filename: string; pages: number[]; text: string; review_status: string; url: string }
type Answer = { question: string; sections: { title: string; text: string; citations: { source_id: string; quote: string }[] }[];
  insufficient_evidence: boolean; missing_information: string; sources: Source[]; elapsed_ms: number; provider: string; model: string }
async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Start or restart the document backend and try again.')
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The request failed. Check your question and try again.')
  return data
}

export function AskDocuments({ onBusyChange }: { onBusyChange?: (busy: boolean) => void }) {
  const [opened, setOpened] = useState(false)
  const sourceDetails = useRef<HTMLDetailsElement>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    if (!opened) return
    const controller = new AbortController()
    // Synchronize provider setup feedback with the config request.
    // oxlint-disable-next-line react/set-state-in-effect
    setLoading(true)
    setError('')
    api<Config>('/api/qa/config', { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setConfig(data)
    }).catch(error => { if (!controller.signal.aborted) setError(error.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [opened, refresh])
  async function ask() {
    setBusy(true); onBusyChange?.(true); setError(''); setAnswer(null)
    try {
      setAnswer(await api<Answer>('/api/qa/ask', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' },
        body: JSON.stringify({ question: question.trim() }) }))
    } catch (error) { setError((error as Error).message) }
    finally { setBusy(false); onBusyChange?.(false) }
  }
  return <section className="pdf-qa" aria-label="Ask my PDFs">
    <Button disabled={busy} aria-expanded={opened} onClick={() => setOpened(!opened)}><MessageSquare size={18} aria-hidden="true" />{opened ? 'Close Q&A' : 'Ask my PDFs'}</Button>
    {opened && <>
      <h3>Ask your Dynamic Programming notes</h3>
      <p className="pdf-muted">Detailed explanations with PDF citations. Your question and selected text passages are processed by your configured model provider.</p>
      {loading && <p role="status">Checking Q&A setup…</p>}
      {error && <p className="pdf-error" role="alert">{error}</p>}
      {!loading && (!config?.configured || error) && <details className="pdf-qa-setup" open={!config?.configured}>
        <summary>Q&A setup</summary><p>Configure Ollama locally or add your Groq API key and model to <code>backend/.env</code>, then restart the backend. Keep the key out of the browser and Git.</p>
        <p>See <code>documentation/model-providers.md</code> for setup instructions.</p>
        <Button variant="secondary" disabled={busy} onClick={() => setRefresh(v => v + 1)}>Refresh Q&A setup</Button>
      </details>}
      {config?.corpus_error && <p className="pdf-error" role="alert">{config.corpus_error}</p>}
      {config && <details><summary>Sources & model</summary><ul>{config.documents.map(doc => <li key={doc.filename}>{doc.filename}</li>)}</ul>
        <p>Hybrid retrieval · {config.provider} · {config.model ?? 'Model not configured'} · Tracing disabled</p>
        <p>Unreviewed excerpts are included and labelled. Saved indexes must be current.</p>
      </details>}
      <form onSubmit={event => { event.preventDefault(); ask() }}>
        <label>Your question<textarea disabled={busy} value={question} maxLength={4000} onChange={event => { setQuestion(event.target.value); setAnswer(null) }} placeholder="How do memoization and tabulation differ?" /></label>
        <Button type="submit" disabled={busy || loading || !config?.configured || !!config.corpus_error || !question.trim()}>{busy ? 'Generating answer…' : 'Ask with citations'}</Button>
      </form>
      {busy && <p role="status">Retrieving passages and generating your answer…</p>}
      {answer && <article className="pdf-answer" aria-label="Cited answer">
        <div className="pdf-index-heading"><h4>{answer.sections.length ? 'Answer' : 'Not enough evidence'}</h4><span className="pdf-badge">{(answer.elapsed_ms / 1000).toFixed(1)} seconds</span></div>
        {answer.insufficient_evidence && <p className="pdf-notice" role="status">{answer.missing_information}</p>}
        {answer.sources.some(source => source.review_status !== 'reviewed') && <p className="pdf-muted">Some retrieved text has not been reviewed. Check the original pages, especially code and formulas.</p>}
        {answer.sections.map((section, index) => <section key={index} className="pdf-answer-section">
          <h4>{section.title}</h4><p className="pdf-answer-text">{section.text}</p>
          <div className="pdf-citation-links">{Array.from(new Set(section.citations.map(c => c.source_id))).map(id => {
            const source = answer.sources.find(s => s.source_id === id)
            return source ? <a key={id} href={`#qa-source-${id}`} onClick={() => {
              if (sourceDetails.current) sourceDetails.current.open = true
              requestAnimationFrame(() => document.getElementById(`qa-source-${id}`)?.focus())
            }}>[{id}] {source.filename}, p. {source.pages.join(', ')}</a> : null
          })}</div>
          <details><summary>Evidence for this section</summary>{section.citations.map((citation, i) => <blockquote key={i}>[{citation.source_id}] {citation.quote}</blockquote>)}</details>
        </section>)}
        {!!answer.sources.length && <details ref={sourceDetails} className="pdf-answer-sources"><summary>Retrieved sources ({answer.sources.length})</summary>
          {answer.sources.map(source => <section key={source.source_id} id={`qa-source-${source.source_id}`} tabIndex={-1}>
            <h4>[{source.source_id}] {source.filename} · PDF page {source.pages.join(', ')}</h4>
            <p className="pdf-muted">{source.review_status === 'reviewed' ? 'Reviewed source' : 'Unreviewed source'}</p>
            <a href={source.url} target="_blank" rel="noreferrer">Open original PDF page</a><pre>{source.text}</pre>
          </section>)}
        </details>}
        <p className="pdf-muted pdf-help">Citation IDs and quoted text are validated. That does not prove every generated claim is supported; inspect the evidence.</p>
      </article>}
    </>}
  </section>
}
