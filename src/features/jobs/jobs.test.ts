import { expect, it } from 'vitest'
import { createEmptyData } from '../../types/defaults'
import { jobApplicationInputSchema } from '../../types/models'
import { applyDataAction } from '../../app/dataActions'
import { getApplicationReminders, getApplicationSummary } from './calculations'
import { exportBackup, loadData, saveData, validateBackup } from '../../storage/storage'

it('migrates v1 data and backups without losing preparation data or rewriting storage on load', () => {
  const current = applyDataAction(createEmptyData(), { type: 'addSession', input: { topic: 'Trees', area: 'Coding', date: '2026-10-27', plannedMinutes: 60 } })
  const { jobApplications: _jobs, ...old } = current
  const legacy = { ...old, schemaVersion: 1 }
  let raw = JSON.stringify(legacy)
  const original = raw
  const port = { getItem: () => raw, setItem: (_key: string, value: string) => { raw = value } }
  expect(loadData(port)).toMatchObject({ status: 'ready', data: current })
  expect(raw).toBe(original)
  expect(validateBackup(JSON.stringify({ exportedAt: '2026-10-27T00:00:00Z', data: legacy }))).toEqual(current)
  saveData(current, original, port)
  expect(JSON.parse(raw).schemaVersion).toBe(2)
  expect(validateBackup(exportBackup(current))).toEqual(current)
  expect(() => validateBackup(JSON.stringify({ exportedAt: '2026-10-27T00:00:00Z', data: { ...legacy, extra: true } }))).toThrow()
})
it('validates submitted dates, reminder actions, links, and required text', () => {
  const job = { company: 'Acme', role: 'Staff Engineer', status: 'Saved', notes: '' }
  expect(jobApplicationInputSchema.safeParse(job).success).toBe(true)
  for (const patch of [{ company: ' ' }, { role: '' }, { status: 'Applied' }, { reminderDate: '2026-10-27' }, { url: 'javascript:alert(1)' }, { applicationDate: '2026-02-30' }]) {
    expect(jobApplicationInputSchema.safeParse({ ...job, ...patch }).success).toBe(false)
  }
})
it('counts submission dates across week/month/year boundaries and preserves historical submissions', () => {
  let data = createEmptyData()
  for (const [status, date] of [['Rejected', '2026-12-28'], ['Withdrawn', '2027-01-01'], ['Applied', '2027-01-03'], ['Applied', '2026-12-27'], ['Applied', '2027-01-04']] as const) {
    data = applyDataAction(data, { type: 'addJobApplication', input: { company: 'Acme', role: 'Engineer', status, applicationDate: date, notes: '' } })
  }
  data = applyDataAction(data, { type: 'addJobApplication', input: { company: 'Beta', role: 'Engineer', status: 'In Progress', notes: '' } })
  expect(getApplicationSummary(data.jobApplications, '2027-01-03')).toEqual({ week: 3, month: 2, total: 4, unfinished: 1, interviewing: 0 })
  const job = data.jobApplications[0]
  const { applicationDate: _date, id: _id, createdAt: _created, updatedAt: _updated, ...input } = job
  data = applyDataAction(data, { type: 'updateJobApplication', id: job.id, input: { ...input, status: 'Withdrawn' } })
  expect(data.jobApplications[0].applicationDate).toBe('2026-12-28')
})
it('groups reminder boundaries and clears reminders without changing status', () => {
  let data = createEmptyData()
  for (const date of ['2026-10-26', '2026-10-27', '2026-11-03', '2026-11-04']) {
    data = applyDataAction(data, { type: 'addJobApplication', input: { company: date, role: 'Engineer', status: 'Saved', notes: '', reminderDate: date, nextAction: 'Finish application' } })
  }
  expect(getApplicationReminders(data.jobApplications, '2026-10-27').due).toHaveLength(2)
  expect(getApplicationReminders(data.jobApplications, '2026-10-27').upcoming).toHaveLength(1)
  data = applyDataAction(data, { type: 'completeApplicationReminder', id: data.jobApplications[0].id })
  expect(data.jobApplications[0]).toMatchObject({ status: 'Saved' })
  expect(data.jobApplications[0].reminderDate).toBeUndefined()
  expect(data.jobApplications[0].nextAction).toBeUndefined()
  expect(getApplicationReminders(data.jobApplications, '2026-10-27').due).toHaveLength(1)
})
