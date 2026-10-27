import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DataProvider } from '../../app/DataProvider'
import { loadData } from '../../storage/storage'
import { SystemDesignLab } from './SystemDesignLab'
import { DESIGN_SECTIONS, DESIGN_CHECKLIST } from './designFields'

beforeEach(() => {
  localStorage.clear()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
const renderLab = () => render(<DataProvider><SystemDesignLab /></DataProvider>)
function savedData() {
  const result = loadData()
  if (result.status === 'error') throw result.error
  return result.data
}
async function createAttempt() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'New attempt' }))
  await user.type(screen.getByLabelText('Problem title'), 'Notification service')
  for (const { label } of DESIGN_SECTIONS) await user.type(screen.getByLabelText(label), `Notes: ${label}`)
  for (const { label } of DESIGN_CHECKLIST) await user.click(screen.getByRole('checkbox', { name: label }))
  await user.selectOptions(screen.getByLabelText('Self-rated confidence'), '4')
  await user.click(screen.getByRole('button', { name: 'Save attempt' }))
}

describe('System Design Lab', () => {
  it('saves all fields, reloads, edits, clears confidence, and deletes with confirmation', async () => {
    const user = userEvent.setup()
    const app = renderLab()
    expect(screen.getByText('Make room for your first design')).toBeInTheDocument()
    await createAttempt()
    const initial = savedData().designAttempts[0]
    for (const { key, label } of DESIGN_SECTIONS) expect(initial[key]).toBe(`Notes: ${label}`)
    expect(Object.values(initial.checklist).every(Boolean)).toBe(true)
    expect(initial.confidence).toBe(4)
    app.unmount()
    renderLab()
    const card = screen.getByRole('article', { name: 'Notification service' })
    expect(within(card).getByText('5 / 5 considered')).toBeInTheDocument()
    await user.click(screen.getByText('Read practice notes'))
    expect(screen.getByText('Notes: Scale estimates')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Edit attempt' }))
    expect(screen.getByLabelText('Architecture notes')).toHaveValue('Notes: Architecture notes')
    await user.clear(screen.getByLabelText('Problem title'))
    await user.type(screen.getByLabelText('Problem title'), 'Chat service')
    await user.click(screen.getByRole('checkbox', { name: 'Security' }))
    await user.selectOptions(screen.getByLabelText('Self-rated confidence'), '')
    await user.click(screen.getByRole('button', { name: 'Save attempt' }))
    expect(savedData().designAttempts[0].id).toBe(initial.id)
    expect(savedData().designAttempts[0].confidence).toBeUndefined()
    expect(screen.getByText('4 / 5 considered')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete attempt' }))
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(savedData().designAttempts).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Delete attempt' }))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    expect(savedData().designAttempts).toHaveLength(0)
    expect(screen.getByText('Make room for your first design')).toBeInTheDocument()
  })
  it('requires a nonblank title but permits an otherwise empty draft', async () => {
    const user = userEvent.setup()
    renderLab()
    await user.click(screen.getByRole('button', { name: 'Start your first attempt' }))
    await user.type(screen.getByLabelText('Problem title'), '   ')
    await user.click(screen.getByRole('button', { name: 'Save attempt' }))
    expect(screen.getByLabelText('Problem title')).toHaveAttribute('aria-invalid', 'true')
    expect(savedData().designAttempts).toHaveLength(0)
    await user.type(screen.getByLabelText('Problem title'), 'URL shortener')
    await user.click(screen.getByRole('button', { name: 'Save attempt' }))
    expect(savedData().designAttempts[0].title).toBe('URL shortener')
    expect(screen.getByText('0 / 5 considered')).toBeInTheDocument()
  })
  it('protects dirty edits on cancel, Escape, and tab close; keep-editing preserves values', async () => {
    const user = userEvent.setup()
    const app = renderLab()
    await user.click(screen.getByRole('button', { name: 'New attempt' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'New attempt' }))
    await user.type(screen.getByLabelText('Problem title'), 'Unsaved draft')
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText('Problem title')).toHaveValue('Unsaved draft')
    const cancel = new Event('cancel', { cancelable: true })
    fireEvent(screen.getByRole('dialog'), cancel)
    expect(cancel.defaultPrevented).toBe(true)
    expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(savedData().designAttempts).toHaveLength(0)
    app.unmount()
    const cleanUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(cleanUnload)
    expect(cleanUnload.defaultPrevented).toBe(false)
  })
  it('preserves saved notes when discarding edits and retries after a failed write', async () => {
    const user = userEvent.setup()
    renderLab()
    await createAttempt()
    const original = savedData().designAttempts[0]
    await user.click(screen.getByRole('button', { name: 'Edit attempt' }))
    await user.clear(screen.getByLabelText('Scale estimates'))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(savedData().designAttempts[0]).toEqual(original)
    await user.click(screen.getByRole('button', { name: 'Edit attempt' }))
    await user.type(screen.getByLabelText('Architecture notes'), '\n<script>example</script>')
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError') })
    try {
      await user.click(screen.getByRole('button', { name: 'Save attempt' }))
      expect(screen.getByRole('alert')).toHaveTextContent('Could not save')
      expect(savedData().designAttempts[0]).toEqual(original)
      expect(screen.getByLabelText('Architecture notes')).toHaveValue('Notes: Architecture notes\n<script>example</script>')
    } finally { spy.mockRestore() }
    await user.click(screen.getByRole('button', { name: 'Save attempt' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByText('Read practice notes'))
    expect(screen.getByText(/<script>example<\/script>/)).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })
})
