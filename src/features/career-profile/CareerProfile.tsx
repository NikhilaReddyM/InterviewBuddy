import { useEffect, useState } from 'react'
import { FileText, Upload, ShieldCheck } from 'lucide-react'
import { ProfileEditor } from './ProfileEditor'
import './career-profile.css'
import { Button } from '../../components/Button'

type Resume = { id: string; filename: string; uploaded_at: string; text: string }
const limit = 5 * 1024 * 1024

async function responseData(response: Response): Promise<Resume[]> {
  if (!response.ok) throw new Error('Could not load resumes. Start the local Python backend and retry.')
  return response.json() as Promise<Resume[]>
}

export function CareerProfile() {
  const [resumes, setResumes] = useState<Resume[]>([])
  const [selected, setSelected] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/resumes', { signal: controller.signal }).then(responseData).then(items => {
      setResumes(items)
      setSelected(items[0]?.id ?? '')
      setError('')
    }).catch(() => {
      if (!controller.signal.aborted) setError('Could not load resumes. Start the local Python backend and retry.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [reload])
  async function upload() {
    if (!file) return
    if (!window.dispatchEvent(new Event('interviewbuddy:before-navigate', { cancelable: true }))) return
    setError('')
    setNotice('')
    if (!(/\.(docx|pdf)$/i.test(file.name)) || file.size > limit) {
      setError('Choose a PDF or DOCX file of 5 MiB or smaller.')
      return
    }
    setBusy(true)
    try {
      const response = await fetch(`/api/resumes?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'X-InterviewBuddy': 'local', 'Content-Type': 'application/octet-stream' }, body: file,
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string }
        throw new Error(response.status === 404 ? 'Resume service not found. Restart the local backend and retry.' : body.detail || 'Resume upload failed. Please retry.')
      }
      const resume = await response.json() as Resume
      setResumes(items => [resume, ...items.filter(item => item.id !== resume.id)])
      setSelected(resume.id)
      setNotice('Resume saved locally. Inspect the extracted text below.')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Resume upload failed. Please retry.')
    } finally { setBusy(false) }
  }
  const resume = resumes.find(item => item.id === selected)
  return <div className="career-page"><div className="career-layout">
    <section className="card career-panel">
      <div className="career-section-heading"><div><p className="eyebrow">STEP 1 · YOUR RESUME</p><h2>Start with your experience</h2></div><FileText size={26} aria-hidden="true" /></div>
      <p>Upload a text-based PDF or Word document (.docx), up to 5 MiB. The original and extracted text stay in the local backend; this step makes no AI calls.</p>
      <details className="career-details"><summary>Extraction details & storage</summary><p>Resume files are separate from browser backups. Text extraction includes paragraphs and tables; images and visual layout may be omitted; Word headers and footers are excluded. PDF resumes support up to 30 pages and require local macOS PDFKit. Check for missing content.</p></details>
      <div className="career-upload"><Upload size={25} aria-hidden="true" /><label htmlFor="resume-file">Choose your resume</label><span>PDF or DOCX · up to 5 MiB</span>
      <input id="resume-file" type="file" accept=".docx,.pdf" disabled={busy || loading} onChange={event => { setFile(event.target.files?.[0] ?? null); setNotice('') }} />
      </div><div className="actions"><Button disabled={!file || busy || loading} onClick={() => void upload()}>{busy ? 'Extracting resume…' : 'Upload and extract'}</Button></div>
      {loading && <p role="status">Loading saved resumes…</p>}
      {error && <div role="alert"><p>{error}</p><Button variant="secondary" disabled={busy} onClick={() => { setLoading(true); setReload(value => value + 1) }}>Reload saved resumes</Button></div>}
      <p className="career-notice" role="status">{notice}</p><p className="career-local"><ShieldCheck size={16} aria-hidden="true" />Upload and text extraction stay on this machine.</p>
    </section>
    <section className="card career-panel">
      <div className="career-section-heading"><h2>Resume source</h2><span className="career-badge">{resumes.length} saved</span></div>
      {resumes.length > 0 ? <><label htmlFor="saved-resume">Saved resume</label><select id="saved-resume" value={selected} onChange={event => { if (window.dispatchEvent(new Event('interviewbuddy:before-navigate', { cancelable: true }))) setSelected(event.target.value) }}>{resumes.map(item => <option key={item.id} value={item.id}>{item.filename}</option>)}</select></> : <div className="career-empty"><FileText size={36} aria-hidden="true" /><h3>Your resume will appear here</h3><p>Upload a file to inspect its text and build your career profile.</p></div>}
      {resume && <><p>Uploaded {new Date(resume.uploaded_at).toLocaleString()}</p><a href={`/api/resumes/${resume.id}/original`}>Download original resume</a><details className="career-details"><summary>Inspect extracted text</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'inherit', maxHeight: '65vh', overflowY: 'auto' }}>{resume.text}</pre></details></>}
    </section>
  </div>{resume && <ProfileEditor key={resume.id} resumeId={resume.id} source={resume.text} />}</div>
}
