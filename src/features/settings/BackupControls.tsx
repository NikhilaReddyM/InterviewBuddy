import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useAppData } from '../../app/dataContext'
import type { AppData } from '../../types/models'
import { createEmptyData } from '../../types/defaults'
import { exportBackup } from '../../storage/storage'
import { downloadText, readBackupFile } from '../../storage/files'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import './backup.css'

type Preview = { data: AppData; filename: string; reset?: boolean }
export function BackupControls() {
  const { data, blocked, rawRecovery, replaceData, error: storageError } = useAppData()
  const [preview, setPreview] = useState<Preview | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [reading, setReading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const request = useRef(0)
  // Ignore file reads that finish after navigation or a newer file selection.
  useEffect(() => () => { request.current += 1 }, [])
  function exportCurrent() {
    try {
      downloadText(exportBackup(data), `interview-prep-backup-${new Date().toISOString().replace(/[:.]/g, '-')}.json`)
      setNotice('Backup download requested. Check your browser downloads.')
      setError('')
    } catch { setError('Could not export a backup. Your saved data has not changed.') }
  }
  function downloadRaw() {
    if (rawRecovery === null) return
    try {
      downloadText(rawRecovery, 'interview-prep-recovery.txt', 'text/plain')
      setNotice('Recovery download requested. Keep this original value before replacing data.')
    } catch { setError('Could not download the recovery value. Your saved data has not changed.') }
  }
  async function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = '' // Permit retrying the same file.
    if (!file) return
    const token = ++request.current
    setReading(true); setError(''); setNotice(''); setPreview(null); setConfirmed(false)
    try {
      const incoming = await readBackupFile(file)
      if (request.current === token) setPreview({ data: incoming, filename: file.name })
    } catch (cause) {
      if (request.current === token) setError(cause instanceof Error ? cause.message : 'Could not import this file.')
    } finally { if (request.current === token) setReading(false) }
  }
  return <section className="card settings-card backup-controls" aria-labelledby="backup-heading">
    <h2 id="backup-heading">Backup & recovery</h2>
    <p>Download a JSON copy of all sessions, resources, design attempts, job applications, availability, and preferences. Keep backups somewhere safe.</p>
    <div className="actions"><Button variant="secondary" disabled={blocked} onClick={exportCurrent}>Export JSON backup</Button></div>
    {blocked && <p className="backup-warning">Saved data could not be loaded. Normal export is disabled to avoid backing up empty defaults. Import a valid backup to recover.</p>}
    {rawRecovery !== null && <Button variant="secondary" onClick={downloadRaw}>Download original saved value</Button>}
    <div className="field"><label htmlFor="backup-file">Import JSON backup</label><input id="backup-file" type="file" accept=".json,application/json" aria-describedby="backup-help" disabled={reading} onChange={selectFile} /><p className="field-hint" id="backup-help">Maximum 5 MiB. Validated before preview. Import replaces all records and preferences; it does not merge them.</p></div>
    {reading && <p role="status">Reading and validating backup…</p>}
    {notice && <p role="status" className="backup-notice">{notice}</p>}
    {error && !preview && <p role="alert" className="field-error">{error}</p>}
    {blocked && rawRecovery !== null && <Button variant="danger" disabled={reading} onClick={() => {
      setPreview({ data: createEmptyData(), filename: '', reset: true }); setConfirmed(false); setError('')
    }}>Start fresh instead</Button>}
    {preview && <Dialog title={preview.reset ? 'Reset unreadable saved data?' : 'Review backup before replacing data'} closeLabel="Cancel" onClose={() => { setPreview(null); setError('') }}>
      {preview.reset ? <p>This removes the unreadable saved value and starts with empty defaults.</p> : <p className="backup-filename">Selected file: {preview.filename}</p>}
      <table className="backup-preview"><caption>Replacement summary</caption><thead><tr><th scope="col">Data</th><th scope="col">Current</th><th scope="col">Incoming</th></tr></thead><tbody>{[
        ['Study sessions', data.sessions.length, preview.data.sessions.length],
        ['Resources', data.resources.length, preview.data.resources.length],
        ['Design attempts', data.designAttempts.length, preview.data.designAttempts.length],
        ['Job applications', data.jobApplications.length, preview.data.jobApplications.length],
        ['Availability overrides', Object.keys(data.availabilityOverrides).length, Object.keys(preview.data.availabilityOverrides).length],
      ].map(([label, current, incoming]) => <tr key={label}><th scope="row">{label}</th><td>{blocked ? 'Unreadable' : current}</td><td>{incoming}</td></tr>)}</tbody></table>
      <p>Theme: {preview.data.preferences.theme}. Start screen: {preview.data.preferences.defaultLandingScreen}. Availability defaults: {preview.data.preferences.defaultWeekdayMinutes} weekday / {preview.data.preferences.defaultWeekendMinutes} weekend minutes.</p>
      <p className="backup-warning">All current records and preferences will be replaced. This cannot be undone without a backup.</p>
      {blocked ? rawRecovery !== null && <Button variant="secondary" onClick={downloadRaw}>Download original saved value first</Button> : <Button variant="secondary" onClick={exportCurrent}>Export current data first</Button>}
      {notice && <p role="status" className="backup-notice">{notice}</p>}
      <label className="backup-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I understand that this replaces all existing data.</label>
      {error && <p role="alert" className="field-error">{error}{storageError && ` ${storageError}`}</p>}
      <Button variant="danger" disabled={!confirmed} onClick={() => {
        if (replaceData(preview.data, confirmed)) {
          setPreview(null); setConfirmed(false); setError('')
          setNotice(preview.reset ? 'Unreadable data replaced with empty defaults.' : 'Backup restored. All records and preferences have been replaced.')
        } else setError('Replacement failed. Existing saved data was not changed. Cancel, reload saved data, and try again.')
      }}>{preview.reset ? 'Reset to empty data' : 'Replace all data'}</Button>
    </Dialog>}
  </section>
}
