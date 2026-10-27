import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ResourceLibrary } from './ResourceLibrary'
import { WeeklyPlanner } from '../planner/WeeklyPlanner'
import { DataProvider } from '../../app/DataProvider'
import { loadData } from '../../storage/storage'

beforeEach(() => {
  localStorage.clear()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
const renderLibrary = () => render(<DataProvider><ResourceLibrary /></DataProvider>)
function savedData() {
  const loaded = loadData()
  if (loaded.status === 'error') throw loaded.error
  return loaded.data
}
async function addResource() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Add resource' }))
  await user.type(screen.getByLabelText('Title'), 'Cache design')
  await user.selectOptions(screen.getByLabelText('Preparation area'), 'System Design')
  await user.selectOptions(screen.getByLabelText('Source'), 'Hello Interview')
  await user.type(screen.getByLabelText('Topic tags'), 'cache, scaling, cache, ')
  await user.type(screen.getByLabelText('URL (optional)'), 'https://example.com/cache')
  await user.type(screen.getByLabelText('Notes or solution text'), '<script>alert(1)</script>\nEviction policies')
  await user.selectOptions(screen.getByLabelText('Confidence'), '3')
  fireEvent.change(screen.getByLabelText('Next revision date (optional)'), { target: { value: '2020-01-01' } })
  await user.click(screen.getByRole('button', { name: 'Save resource' }))
}

describe('resource library', () => {
  it('creates, edits, clears optional fields, and persists after remount', async () => {
    const user = userEvent.setup()
    const app = renderLibrary()
    expect(screen.getByText('Your library starts here')).toBeInTheDocument()
    await addResource()
    expect(savedData().resources[0].tags).toEqual(['cache', 'scaling'])
    expect(screen.getByText(/Revision due:/)).toBeInTheDocument()
    await user.click(screen.getByText('Read notes / solution'))
    expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
    expect(screen.getByRole('link', { name: 'Open resource ↗' })).toHaveAttribute('rel', 'noopener noreferrer')
    await user.click(screen.getByRole('button', { name: 'Edit resource' }))
    await user.clear(screen.getByLabelText('Title'))
    await user.type(screen.getByLabelText('Title'), 'Cache notes')
    await user.clear(screen.getByLabelText('URL (optional)'))
    fireEvent.change(screen.getByLabelText('Next revision date (optional)'), { target: { value: '' } })
    await user.selectOptions(screen.getByLabelText('Confidence'), '')
    await user.selectOptions(screen.getByLabelText('Status'), 'Reviewed')
    await user.click(screen.getByRole('button', { name: 'Save resource' }))
    app.unmount()
    renderLibrary()
    const resource = savedData().resources[0]
    expect(resource.title).toBe('Cache notes')
    expect(resource.url).toBeUndefined()
    expect(resource.nextRevisionDate).toBeUndefined()
    expect(resource.confidence).toBeUndefined()
    expect(within(screen.getByRole('article', { name: 'Cache notes' })).getByText('Reviewed')).toBeInTheDocument()
  })
  it('searches notes, combines filters, and resets no-match results', async () => {
    const user = userEvent.setup()
    renderLibrary()
    await addResource()
    await user.type(screen.getByLabelText('Search resources'), 'eviction')
    expect(screen.getByRole('article', { name: 'Cache design' })).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Filter by source'), 'LeetCode')
    expect(screen.getByText('No matching resources')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reset search and filters' }))
    await user.selectOptions(screen.getByLabelText('Filter by revision'), 'due')
    expect(screen.getByRole('article', { name: 'Cache design' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByLabelText('Filter by revision')).toHaveValue('all')
  })
  it('schedules a linked session and preserves snapshots when deleting the resource', async () => {
    const user = userEvent.setup()
    const app = renderLibrary()
    await addResource()
    const resource = savedData().resources[0]
    await user.click(screen.getByRole('button', { name: 'Schedule session' }))
    expect(screen.getByLabelText('Topic')).toHaveValue('Cache design')
    expect(screen.getByLabelText('Preparation area')).toHaveValue('System Design')
    expect(screen.getByLabelText('Resource link (optional)')).toHaveValue('https://example.com/cache')
    await user.click(screen.getByRole('button', { name: 'Save session' }))
    expect(savedData().sessions[0].resourceId).toBe(resource.id)
    expect(savedData().resources[0]).toEqual(resource)
    await user.click(screen.getByRole('button', { name: 'Delete resource' }))
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(savedData().resources).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Delete resource' }))
    await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
    expect(savedData().resources).toHaveLength(0)
    expect(savedData().sessions[0].resourceId).toBeUndefined()
    expect(savedData().sessions[0].resourceUrl).toBe(resource.url)
    app.unmount()
    render(<DataProvider><WeeklyPlanner /></DataProvider>)
    expect(within(screen.getByRole('article', { name: 'Cache design' })).getByText('System Design · 60 min planned')).toBeInTheDocument()
  })
  it('validates title and unsafe URLs and leaves unsaved forms open on storage failure', async () => {
    const user = userEvent.setup()
    renderLibrary()
    await user.click(screen.getByRole('button', { name: 'Add resource' }))
    await user.type(screen.getByLabelText('URL (optional)'), 'javascript:alert(1)')
    await user.click(screen.getByRole('button', { name: 'Save resource' }))
    expect(screen.getByLabelText('Title')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('URL (optional)')).toHaveAttribute('aria-invalid', 'true')
    expect(savedData().resources).toHaveLength(0)
    await user.type(screen.getByLabelText('Title'), 'Keep these notes')
    await user.clear(screen.getByLabelText('URL (optional)'))
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError') })
    try {
      await user.click(screen.getByRole('button', { name: 'Save resource' }))
      expect(screen.getByRole('alert')).toHaveTextContent('Could not save')
      expect(screen.getByLabelText('Title')).toHaveValue('Keep these notes')
    } finally { spy.mockRestore() }
    await user.click(screen.getByRole('button', { name: 'Save resource' }))
    expect(savedData().resources).toHaveLength(1)
  })
})
