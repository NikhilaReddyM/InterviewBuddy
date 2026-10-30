import { useEffect, useState } from 'react'
import { CheckCircle2, Plus, Sparkles, Trash2 } from 'lucide-react'
import { Button } from '../../components/Button'

const categories = ['experience', 'skills', 'education', 'projects', 'achievements'] as const
type Category = typeof categories[number]
type Fact = { category: Category; text: string; evidence: string }
type Preferences = { target_roles: string; locations: string; remote: string; exclusions: string }
type Profile = { facts: Fact[]; preferences: Preferences; revision: number; confirmed_at: string | null }

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: unknown }
    throw new Error(response.status === 404 ? 'Profile service not found. Restart the local backend and reload.' : typeof body.detail === 'string' ? body.detail : 'Could not complete this request. Check your entries and retry.')
  }
  return response.json() as Promise<T>
}

export function ProfileEditor({ resumeId, source }: { resumeId: string; source: string }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reload, setReload] = useState(0)
  const [failedAction, setFailedAction] = useState<'generate' | 'save' | 'confirm' | null>(null)
  const [showSource, setShowSource] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    request<Profile | null>(`/api/resumes/${resumeId}/profile`, { signal: controller.signal }).then(setProfile).catch(failure => {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Could not load profile.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [resumeId, reload])
  useEffect(() => {
    if (!dirty) return
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const navigate = (event: Event) => { if (!window.confirm('Discard unsaved profile changes?')) event.preventDefault() }
    window.addEventListener('beforeunload', unload)
    window.addEventListener('interviewbuddy:before-navigate', navigate)
    return () => { window.removeEventListener('beforeunload', unload); window.removeEventListener('interviewbuddy:before-navigate', navigate) }
  }, [dirty])
  function change(next: Profile) { setProfile(next); setDirty(true); setNotice('') }
  function editFact(index: number, patch: Partial<Fact>) {
    if (profile) change({ ...profile, facts: profile.facts.map((fact, i) => i === index ? { ...fact, ...patch } : fact) })
  }
  async function act(action: 'generate' | 'save' | 'confirm') {
    setBusy(true); setError(''); setNotice(''); setFailedAction(null)
    try {
      const next = await request<Profile>(`/api/resumes/${resumeId}/profile${action === 'generate' ? '/generate' : ''}`, {
        method: action === 'generate' ? 'POST' : 'PUT',
        headers: { 'X-InterviewBuddy': 'local', 'Content-Type': 'application/json' },
        ...(action === 'generate' ? {} : { body: JSON.stringify({ facts: profile?.facts, preferences: profile?.preferences, revision: profile?.revision, confirm: action === 'confirm' }) }),
      })
      setProfile(next); setDirty(false)
      setNotice(action === 'generate' ? 'Profile generated. Review every fact and its evidence before confirming.' : action === 'confirm' ? 'Profile confirmed and saved.' : 'Draft saved. Confirm when your review is complete.')
    } catch (failure) { setFailedAction(action); setError(failure instanceof Error ? failure.message : 'Request failed. Please retry.') }
    finally { setBusy(false) }
  }
  const invalid = profile?.facts.some(fact => !fact.text.trim() || !fact.evidence.trim() || !source.includes(fact.evidence))
  return <section className="card career-editor" aria-busy={loading || busy}>
    <div className="career-section-heading"><div><p className="eyebrow">STEP 2 · REVIEW & CONFIRM</p><h2>Your career profile</h2></div>{profile && <span className="career-badge">{dirty ? 'Unsaved changes' : profile.confirmed_at ? 'Confirmed' : 'Draft'}</span>}</div>
    {loading ? <p role="status">Loading profile…</p> : !profile ? <div className="career-intro"><Sparkles size={28} aria-hidden="true" /><h3>Turn your resume into a reusable profile</h3><p>Generate experience, skills, education, projects, and achievements with quotes you can verify.</p><p className="subtle">Generating sends this resume’s extracted text to your configured Groq model. Files stay local and cloud tracing is disabled.</p><Button disabled={busy} onClick={() => void act('generate')}>{busy ? 'Generating profile…' : 'Generate profile'}</Button></div> : <>
      <p className="subtle">Correct or remove facts below. Each supporting quote must appear exactly in the resume. Quote matching checks provenance; you still need to check that the quote supports the statement.</p>
      {categories.map(category => <div className="career-category" key={category}><div className="career-section-heading"><h3>{category}</h3><Button variant="secondary" disabled={busy} onClick={() => change({ ...profile, facts: [...profile.facts, { category, text: '', evidence: '' }] })}><Plus size={15} />Add fact</Button></div>
        {!profile.facts.some(fact => fact.category === category) && <p className="subtle">No facts extracted in this category.</p>}
        {profile.facts.map((fact, index) => fact.category === category && <div className="career-fact" key={index}>
          <div className="field"><label htmlFor={`fact-${index}`}>Fact</label><textarea id={`fact-${index}`} rows={3} value={fact.text} disabled={busy} maxLength={3000} onChange={event => editFact(index, { text: event.target.value })} /></div>
          <div className="field"><label htmlFor={`evidence-${index}`}>Supporting resume quote</label><textarea id={`evidence-${index}`} rows={2} value={fact.evidence} disabled={busy} maxLength={4000} onChange={event => editFact(index, { evidence: event.target.value })} />{fact.evidence && !source.includes(fact.evidence) && <p className="field-error">Paste an exact quote from the resume text.</p>}</div>
          <Button variant="secondary" aria-label={`Remove ${category} fact ${index + 1}`} disabled={busy} onClick={() => change({ ...profile, facts: profile.facts.filter((_, i) => i !== index) })}><Trash2 size={15} />Remove</Button>
        </div>)}
      </div>)}
      <div className="career-preferences"><p className="eyebrow">YOUR PREFERENCES</p><h3>What are you looking for?</h3><p className="subtle">These answers come from you, separately from your resume. Leave anything undecided blank.</p><div className="career-preference-grid">
        {(['target_roles', 'locations', 'exclusions'] as const).map(key => <div className="field" key={key}><label htmlFor={key}>{key === 'target_roles' ? 'Target roles' : key === 'locations' ? 'Preferred locations' : 'Roles, companies, or conditions to exclude'}</label><textarea id={key} rows={2} maxLength={2000} disabled={busy} value={profile.preferences[key]} onChange={event => change({ ...profile, preferences: { ...profile.preferences, [key]: event.target.value } })} /></div>)}
        <div className="field"><label htmlFor="remote-preference">Work arrangement</label><select id="remote-preference" disabled={busy} value={profile.preferences.remote} onChange={event => change({ ...profile, preferences: { ...profile.preferences, remote: event.target.value } })}>{['unspecified', 'remote', 'hybrid', 'onsite', 'flexible'].map(value => <option key={value} value={value}>{value === 'unspecified' ? 'Not decided' : value === 'onsite' ? 'On-site' : value[0].toUpperCase() + value.slice(1)}</option>)}</select></div>
      </div></div>
      <div className="career-save-bar"><p>{dirty ? 'Changes need saving and confirmation.' : profile.confirmed_at ? 'You have reviewed and confirmed this profile.' : 'Review the facts before confirming your profile.'}</p><div className="actions"><Button variant="secondary" disabled={busy || invalid} onClick={() => void act('save')}>Save draft</Button><Button disabled={busy || invalid || !profile.facts.length} onClick={() => void act('confirm')}><CheckCircle2 size={17} />{busy ? 'Saving…' : 'Confirm profile'}</Button></div></div>
    </>}
    {error && <div className="career-error" role="alert">
      <h3>{failedAction === 'generate' ? 'We couldn’t create a verified profile' : failedAction ? 'Your changes couldn’t be saved' : 'We couldn’t load your profile'}</h3>
      <p>{failedAction === 'generate' ? 'No new profile was saved. Your uploaded resume is still available.' : failedAction ? 'Your edits are still on this screen. Try saving again; if another tab changed this profile, copy your edits before reloading.' : 'Check that the local backend is running, then reload your profile.'}</p>
      {failedAction === 'generate' && <p>Try again first. If it fails again, inspect the resume text below for missing or garbled content. You can upload a clearer PDF or DOCX using the upload panel above.</p>}
      <div className="actions">
        {failedAction && <Button disabled={busy} onClick={() => void act(failedAction)}>{failedAction === 'generate' ? 'Try generating again' : 'Try saving again'}</Button>}
        <Button variant="secondary" disabled={busy} onClick={() => setShowSource(value => !value)}>{showSource ? 'Hide resume text' : 'Inspect resume text'}</Button>
        <Button variant="secondary" disabled={busy} onClick={() => { if (dirty && !window.confirm('Discard unsaved changes and reload?')) return; setError(''); setFailedAction(null); setDirty(false); setLoading(true); setReload(value => value + 1) }}>Reload profile</Button>
      </div>
      <details className="career-error-details"><summary>Technical details</summary><p>{error}</p></details>
    </div>}
    {showSource && <section className="career-source-review"><h3>Check your extracted resume</h3><p>Compare this with your original resume. Names, roles, dates, and achievements should be readable and complete.</p><pre>{source}</pre></section>}
    {notice && <p className="career-notice" role="status">{notice}</p>}
  </section>
}
