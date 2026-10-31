import { useState } from 'react'
import { Button } from '../../components/Button'

type Job = { candidate_id: string; source: string; source_id: string; company: string; role: string; url: string; location: string; workplace: string; description: string; retrieved_at: string }
type Catalog = { jobs: Job[]; total_matches: number; limited: boolean; sources: { source: string; count: number; status: string }[]; errors: string[]; model_calls: number }
export function JobCatalog({ resumes, onSaved }: { resumes: { id: string; filename: string }[]; onSaved: (workspaceId: string) => void }) {
  const [filter, setFilter] = useState({ q: 'engineer', location: 'US', workplace: 'any' })
  const [result, setResult] = useState<Catalog | null>(null)
  const [resume, setResume] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState<Record<string, string>>({})
  async function browse() {
    setBusy(true); setError('')
    try {
      const response = await fetch(`/api/job-catalog?${new URLSearchParams({ ...filter, limit: '50' })}`)
      if (!response.ok) throw new Error('Could not load public listings. Restart the backend and retry.')
      setResult(await response.json() as Catalog)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load jobs.') }
    finally { setBusy(false) }
  }
  async function save(job: Job) {
    setBusy(true); setError('')
    try {
      // Stable identity uses the public job URL and selected resume, across refreshes.
      const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${resume}:${job.url}`))
      const key = 'catalog:' + Array.from(new Uint8Array(bytes)).map(value => value.toString(16).padStart(2, '0')).join('')
      const response = await fetch('/api/workspaces', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify({ resume_id: resume, company: job.company, role: job.role, description: job.description + `\n\nSource: ${job.source}\nRequired location: ${job.location}\nWork arrangement: ${job.workplace}`, url: job.url, request_id: key }) })
      const payload = await response.json() as { id?: string; detail?: string }
      if (!response.ok || !payload.id) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Could not save this listing. Confirm your Career Profile first.')
      setSaved(value => ({ ...value, [job.candidate_id + resume]: payload.id! }))
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not save job.') }
    finally { setBusy(false) }
  }
  return <section className="card career-panel"><div className="career-section-heading"><div><p className="eyebrow">NO MODEL QUOTA NEEDED</p><h2>Browse public job listings</h2></div></div>
    <p>Search cached public listings without calling a model. Includes selected employer boards on Greenhouse and Ashby, plus Remotive and Arbeitnow. Save a job to prepare its application later.</p>
    <form onSubmit={event => { event.preventDefault(); void browse() }}><fieldset disabled={busy} className="workspace-fields"><div className="career-preference-grid"><div className="field"><label htmlFor="catalog-query">Role or keywords</label><input id="catalog-query" maxLength={200} value={filter.q} onChange={event => setFilter({ ...filter, q: event.target.value })} /></div><div className="field"><label htmlFor="catalog-location">Location</label><input id="catalog-location" maxLength={200} value={filter.location} onChange={event => setFilter({ ...filter, location: event.target.value })} placeholder="US, Europe, or a city" /></div><div className="field"><label htmlFor="catalog-workplace">Work arrangement</label><select id="catalog-workplace" value={filter.workplace} onChange={event => setFilter({ ...filter, workplace: event.target.value })}>{['any', 'hybrid', 'remote', 'onsite', 'unknown'].map(value => <option key={value} value={value}>{value === 'unknown' ? 'Not specified' : value}</option>)}</select></div></div><Button type="submit">{busy ? 'Loading listings…' : 'Browse jobs — no AI'}</Button></fieldset></form>
    {error && <p role="alert" className="career-error">{error}</p>}
    {result && <><p role="status">{result.total_matches} listings match your filters. Showing {result.jobs.length}. No model calls were made.</p><p className="subtle">This covers the configured employer boards, not all jobs on Greenhouse or Ashby. Unknown work arrangements are not treated as on-site. Verify hiring eligibility and availability at the original listing.</p><details className="career-details"><summary>Source coverage</summary>{result.sources.map(source => <p key={source.source}>{source.source}: {source.count} listings · {source.status}</p>)}{result.errors.map((message, index) => <p key={index}>{message}</p>)}</details>
      <div className="field"><label htmlFor="catalog-profile">Confirmed profile for saving jobs</label><select id="catalog-profile" value={resume} onChange={event => setResume(event.target.value)}><option value="">Choose a resume</option>{resumes.map(item => <option key={item.id} value={item.id}>{item.filename}</option>)}</select></div>
      {!result.sources.some(source => source.status === 'available') && <p role="alert">All configured sources are currently unavailable. Check source coverage and try again later; changing your profile will not fix a source outage.</p>}
      {!result.jobs.length && result.sources.some(source => source.status === 'available') && <p>No listings found. Try fewer keywords, a broader location, or include unspecified work arrangements.</p>}
      {result.jobs.map(job => <article className="career-fact" key={job.candidate_id}><h3>{job.company} · {job.role}</h3><p>{job.location} · {job.workplace === 'unknown' ? 'Work arrangement not specified' : job.workplace}</p><p className="subtle">Source: {job.source} · Retrieved {new Date(job.retrieved_at).toLocaleString()}</p><div className="actions"><a className="button button--secondary" href={job.url} target="_blank" rel="noreferrer">Original application</a>{saved[job.candidate_id + resume] ? <Button variant="secondary" onClick={() => onSaved(saved[job.candidate_id + resume])}>Open saved workspace</Button> : <Button variant="secondary" disabled={busy || !resume} onClick={() => void save(job)}>Save job for later</Button>}</div><details className="career-details"><summary>Job description</summary><pre className="review-draft-text">{job.description}</pre></details></article>)}
    </>}
  </section>
}
