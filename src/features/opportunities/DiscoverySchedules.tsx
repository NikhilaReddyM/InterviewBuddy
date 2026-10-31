import { useState } from 'react'
import { Button } from '../../components/Button'

type Config = { name: string; resume_id: string; timezone: string; local_time: string; weekdays: number[]; max_applications: number; enabled: boolean }
type Schedule = Config & { id: string; revision: number; next_run_at: string | null; runs?: { id: string; scheduled_for: string; status: string; message: string; started_at?: string; batch_id?: string | null }[] }
const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
async function request<T>(url: string, body?: unknown, method = 'POST'): Promise<T> {
  const response = await fetch(url, body === undefined ? undefined : { method, headers: { 'Content-Type': 'application/json', 'X-InterviewBuddy': 'local' }, body: JSON.stringify(body) })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the schedule fields, selected days, and timezone, then try again.')
  return data as T
}
function configOf(value: Config): Config {
  return { name: value.name, resume_id: value.resume_id, timezone: value.timezone, local_time: value.local_time, weekdays: value.weekdays, max_applications: value.max_applications, enabled: value.enabled }
}
export function DiscoverySchedules({ resumes }: { resumes: { id: string; filename: string }[] }) {
  const [schedules, setSchedules] = useState<Schedule[] | null>(null)
  const [editing, setEditing] = useState<Schedule | null>(null)
  const [form, setForm] = useState<Config>({ name: 'Weekday job discovery', resume_id: '', timezone: 'America/New_York', local_time: '09:00', weekdays: [0, 1, 2, 3, 4], max_applications: 1, enabled: false })
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await work() } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update schedules.') }
    finally { setBusy(false) }
  }
  async function load() { setSchedules(await request<Schedule[]>('/api/discovery-schedules')) }
  return <section className="card career-panel"><div className="career-section-heading"><h2>Scheduled discovery</h2><Button variant="secondary" disabled={busy} onClick={() => void action(load)}>{schedules === null ? 'Configure schedules' : 'Refresh schedules'}</Button></div>
    <p>Run fresh discovery on selected days using your latest confirmed profile and review reminder preferences. Scheduled searches use Groq quota. The local backend and computer must be running and awake.</p>
    <p className="subtle">Groq cooldown retries remain manual. Each scheduled time starts at most one new batch. Pausing a schedule stops future runs; an already-running batch may continue.</p>
    {schedules !== null && <><div>{schedules.length === 0 && <p>No schedules yet. Nothing is enabled until you choose to enable it.</p>}{schedules.map(schedule => <article className="career-fact" key={schedule.id}><h3>{schedule.name}</h3><p>{schedule.enabled ? 'Enabled' : 'Paused'} · {schedule.weekdays.map(day => days[day]).join(', ')} at {schedule.local_time} · {schedule.timezone}</p><p>{schedule.next_run_at ? `Next run: ${new Date(schedule.next_run_at).toLocaleString(undefined, { timeZone: schedule.timezone, timeZoneName: 'short' })}` : 'No run scheduled while paused.'}</p><div className="actions"><Button disabled={busy} variant="secondary" onClick={() => { setEditing(schedule); setForm(configOf(schedule)); setKey(crypto.randomUUID()); setNotice('') }}>Edit schedule</Button><Button disabled={busy} variant="secondary" onClick={() => void action(async () => { await request(`/api/discovery-schedules/${schedule.id}`, { ...configOf(schedule), enabled: !schedule.enabled, revision: schedule.revision }, 'PUT'); await load(); setNotice(schedule.enabled ? 'Schedule paused. Future runs are disabled.' : 'Schedule enabled. Check the next run time above.') })}>{schedule.enabled ? 'Pause schedule' : 'Enable schedule'}</Button></div>
      {!!schedule.runs?.length && <details className="career-details"><summary>Recent scheduled runs</summary>{schedule.runs.map(run => <div key={run.id}><p>Scheduled for {new Date(run.scheduled_for).toLocaleString(undefined, { timeZone: schedule.timezone, timeZoneName: 'short' })} · <strong>{run.status}</strong></p><p>{run.message}</p>{run.started_at && <p className="subtle">Started: {new Date(run.started_at).toLocaleString(undefined, { timeZone: schedule.timezone, timeZoneName: 'short' })}</p>}{run.batch_id && <a href="#discovery-history">View saved discovery history · {run.batch_id.slice(0, 8)}</a>}</div>)}</details>}
    </article>)}</div>
    <form onSubmit={event => { event.preventDefault(); void action(async () => {
      await request(editing ? `/api/discovery-schedules/${editing.id}` : '/api/discovery-schedules', editing ? { ...form, revision: editing.revision } : { ...form, request_id: key }, editing ? 'PUT' : 'POST')
      await load(); setNotice(form.enabled ? 'Schedule saved and enabled. Check its next run time above.' : 'Schedule saved paused. Enable it when ready.'); setEditing(null); setForm({ ...form, enabled: false }); setKey(crypto.randomUUID())
    }) }}><fieldset disabled={busy} className="workspace-fields"><h3>{editing ? 'Edit recurring discovery' : 'Create recurring discovery'}</h3><div className="career-preference-grid"><div className="field"><label htmlFor="schedule-name">Schedule name</label><input id="schedule-name" required maxLength={120} value={form.name} onChange={event => { setForm({ ...form, name: event.target.value }); setKey(crypto.randomUUID()) }} /></div><div className="field"><label htmlFor="schedule-profile">Confirmed resume profile</label><select id="schedule-profile" required value={form.resume_id} onChange={event => { setForm({ ...form, resume_id: event.target.value }); setKey(crypto.randomUUID()) }}><option value="">Choose a resume</option>{resumes.map(resume => <option key={resume.id} value={resume.id}>{resume.filename}</option>)}</select></div><div className="field"><label htmlFor="schedule-clock">Run at</label><input id="schedule-clock" required type="time" value={form.local_time} onChange={event => { setForm({ ...form, local_time: event.target.value }); setKey(crypto.randomUUID()) }} /></div><div className="field"><label htmlFor="schedule-zone">Schedule timezone</label><input id="schedule-zone" required value={form.timezone} onChange={event => { setForm({ ...form, timezone: event.target.value }); setKey(crypto.randomUUID()) }} /></div><div className="field"><label htmlFor="schedule-limit">Applications per scheduled run</label><select id="schedule-limit" value={form.max_applications} onChange={event => { setForm({ ...form, max_applications: Number(event.target.value) }); setKey(crypto.randomUUID()) }}>{[1, 2, 3].map(value => <option key={value} value={value}>{value}</option>)}</select></div></div>
      <fieldset className="schedule-days"><legend>Run on</legend>{days.map((day, index) => <label key={day}><input type="checkbox" checked={form.weekdays.includes(index)} onChange={event => { setForm({ ...form, weekdays: event.target.checked ? [...form.weekdays, index].sort() : form.weekdays.filter(value => value !== index) }); setKey(crypto.randomUUID()) }} />{day}</label>)}</fieldset>
      <label className="agent-confirm"><input type="checkbox" checked={form.enabled} onChange={event => { setForm({ ...form, enabled: event.target.checked }); setKey(crypto.randomUUID()) }} />Enable scheduled discovery using my confirmed profile</label>
      <div className="actions"><Button disabled={!form.weekdays.length} type="submit">{editing ? 'Save schedule changes' : 'Save schedule'}</Button>{editing && <Button variant="secondary" onClick={() => { setEditing(null); setForm({ ...form, enabled: false }); setKey(crypto.randomUUID()) }}>Cancel editing</Button>}</div>
    </fieldset></form></>}
    {error && <p className="career-error" role="alert">{error}</p>}{notice && <p role="status" className="career-notice">{notice}</p>}
  </section>
}
