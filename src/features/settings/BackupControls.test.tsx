import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DataProvider } from '../../app/DataProvider'
import { createEmptyData, createEmptyChecklist } from '../../types/defaults'
import { applyDataAction } from '../../app/dataActions'
import { exportBackup, loadData, MAX_BACKUP_BYTES, STORAGE_KEY, validateBackup } from '../../storage/storage'
import { BackupControls } from './BackupControls'

const NativeURL = URL
let downloaded: Blob | undefined
beforeEach(() => {
  localStorage.clear()
  downloaded = undefined
  vi.stubGlobal('URL', Object.assign(class extends NativeURL {}, {
    createObjectURL: vi.fn((blob: Blob) => { downloaded = blob; return 'blob:test' }),
    revokeObjectURL: vi.fn(),
  }))
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
const renderBackup = () => render(<DataProvider><BackupControls /></DataProvider>)
function incomingData() {
  let data = applyDataAction(createEmptyData(), { type: 'addResource', input: { title: 'Cache', area: 'System Design', tags: ['cache'], source: 'Other', notes: 'My notes', status: 'In Progress' } })
  data = applyDataAction(data, { type: 'addSession', input: { topic: 'Cache', area: 'System Design', date: '2026-10-27', plannedMinutes: 60, resourceId: data.resources[0].id } })
  data = applyDataAction(data, { type: 'addDesignAttempt', input: { title: 'Chat', requirementsAndAssumptions: '', scaleEstimates: '', apisAndDataModel: '', architectureNotes: '', tradeoffsAndFailureScenarios: '', missedAndNextSteps: '', checklist: createEmptyChecklist() } })
  data = applyDataAction(data, { type: 'addJobApplication', input: { company: 'Acme', role: 'Staff Engineer', status: 'Applied', applicationDate: '2026-10-27', notes: 'Submitted manually', nextAction: 'Follow up', reminderDate: '2026-11-03' } })
  data.preferences.theme = 'dark'
  data.availabilityOverrides['2026-10-27'] = 100
  return data
}
function text(blob: Blob) {
  return new Promise<string>((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blob) })
}
async function upload(raw = exportBackup(incomingData())) {
  await userEvent.upload(screen.getByLabelText('Import JSON backup'), new File([raw], 'backup.json', { type: 'application/json' }))
}

describe('Backup controls', () => {
  it('exports a validated backup without modifying storage', async () => {
    const data = incomingData()
    const original = JSON.stringify(data)
    localStorage.setItem(STORAGE_KEY, original)
    renderBackup()
    await userEvent.click(screen.getByRole('button', { name: 'Export JSON backup' }))
    expect(validateBackup(await text(downloaded!))).toEqual(data)
    expect(localStorage.getItem(STORAGE_KEY)).toBe(original)
    expect(screen.getByRole('status')).toHaveTextContent('download requested')
  })
  it('previews, cancels, and restores every collection only after acknowledgment', async () => {
    const user = userEvent.setup()
    const original = createEmptyData()
    localStorage.setItem(STORAGE_KEY, JSON.stringify(original))
    const app = renderBackup()
    await upload()
    let dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('table')).toHaveTextContent('Study sessions')
    expect(within(dialog).getByRole('button', { name: 'Replace all data' })).toBeDisabled()
    expect(loadData()).toMatchObject({ data: original })
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(loadData()).toMatchObject({ data: original })
    const incoming = incomingData()
    await upload(exportBackup(incoming))
    dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Export current data first' }))
    expect(validateBackup(await text(downloaded!))).toEqual(original)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Replace all data' }))
    expect(loadData()).toMatchObject({ data: incoming })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    app.unmount()
    renderBackup()
    expect(loadData()).toMatchObject({ data: incoming })
  })
  it.each(['broken', '{}', '{"exportedAt":"2026-10-27T00:00:00Z","data":{"schemaVersion":99}}'])(
    'rejects invalid files without changing existing data: %s', async (raw) => {
      const original = JSON.stringify(incomingData())
      localStorage.setItem(STORAGE_KEY, original)
      renderBackup()
      await upload(raw)
      expect(await screen.findByRole('alert')).toBeInTheDocument()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(localStorage.getItem(STORAGE_KEY)).toBe(original)
    },
  )
  it('rejects oversized files before reading them', async () => {
    renderBackup()
    await upload('a'.repeat(MAX_BACKUP_BYTES + 1))
    expect(await screen.findByRole('alert')).toHaveTextContent('5 MiB')
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
  it('preserves current data on write failure and supports retry', async () => {
    const user = userEvent.setup()
    const original = JSON.stringify(createEmptyData())
    localStorage.setItem(STORAGE_KEY, original)
    renderBackup()
    await upload()
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('checkbox'))
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError') })
    await user.click(screen.getByRole('button', { name: 'Replace all data' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Replacement failed')
    expect(localStorage.getItem(STORAGE_KEY)).toBe(original)
    spy.mockRestore()
    await user.click(screen.getByRole('button', { name: 'Replace all data' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(loadData()).toMatchObject({ data: { preferences: { theme: 'dark' } } })
  })
  it('recovers corrupt storage without exporting misleading empty defaults', async () => {
    const user = userEvent.setup()
    localStorage.setItem(STORAGE_KEY, 'corrupt original')
    renderBackup()
    expect(screen.getByRole('button', { name: 'Export JSON backup' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Download original saved value' }))
    expect(await text(downloaded!)).toBe('corrupt original')
    await upload()
    await screen.findByRole('dialog')
    expect(screen.getAllByText('Unreadable')).toHaveLength(5)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Replace all data' }))
    expect(screen.getByRole('button', { name: 'Export JSON backup' })).toBeEnabled()
    expect(loadData()).toMatchObject({ status: 'ready' })
  })
  it('requires confirmation to reset corrupt data and permits cancellation', async () => {
    const user = userEvent.setup()
    localStorage.setItem(STORAGE_KEY, 'broken')
    renderBackup()
    await user.click(screen.getByRole('button', { name: 'Start fresh instead' }))
    expect(screen.getByRole('button', { name: 'Reset to empty data' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(localStorage.getItem(STORAGE_KEY)).toBe('broken')
    await user.click(screen.getByRole('button', { name: 'Start fresh instead' }))
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Reset to empty data' }))
    expect(loadData()).toMatchObject({ data: createEmptyData() })
  })
  it('rejects stale-tab replacement and leaves the newer saved value intact', async () => {
    const user = userEvent.setup()
    renderBackup()
    await upload()
    await screen.findByRole('dialog')
    const other = JSON.stringify(incomingData())
    localStorage.setItem(STORAGE_KEY, other)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Replace all data' }))
    expect(screen.getByRole('alert')).toHaveTextContent('another tab')
    expect(localStorage.getItem(STORAGE_KEY)).toBe(other)
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
  })
})
