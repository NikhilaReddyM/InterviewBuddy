import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { Dashboard } from './Dashboard'
import { DataProvider } from '../../app/DataProvider'
import { createEmptyData } from '../../types/defaults'
import { applyDataAction } from '../../app/dataActions'
import { STORAGE_KEY } from '../../storage/storage'
import { calendarDate } from '../../utils/dates'

beforeEach(() => {
  localStorage.clear()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
it('shows empty states, all areas, and working navigation actions', async () => {
  const user = userEvent.setup()
  const navigate = vi.fn()
  render(<DataProvider><Dashboard onNavigate={navigate} /></DataProvider>)
  expect(screen.getByText('A fresh space for today')).toBeInTheDocument()
  expect(screen.getByText('No revisions due soon')).toBeInTheDocument()
  expect(screen.getAllByRole('progressbar')).toHaveLength(7)
  await user.click(screen.getByRole('button', { name: 'Open weekly planner' }))
  expect(navigate).toHaveBeenLastCalledWith('planner')
  await user.click(screen.getByRole('button', { name: 'Save a resource' }))
  expect(navigate).toHaveBeenLastCalledWith('resources')
  await user.click(screen.getByRole('button', { name: 'Practice system design' }))
  expect(navigate).toHaveBeenLastCalledWith('design-lab')
})
it('adds a session then completes and undoes it with consistent totals after remount', async () => {
  const user = userEvent.setup()
  const app = render(<DataProvider><Dashboard onNavigate={() => {}} /></DataProvider>)
  await user.click(screen.getByRole('button', { name: 'Add session' }))
  await user.type(screen.getByLabelText('Topic'), 'Graphs')
  await user.click(screen.getByRole('button', { name: 'Save session' }))
  const summary = () => within(screen.getByRole('region', { name: 'Weekly summary' }))
  expect(summary().getByText('60')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Mark complete' }))
  await user.clear(screen.getByLabelText('Actual minutes'))
  await user.type(screen.getByLabelText('Actual minutes'), '80')
  await user.selectOptions(screen.getByLabelText('Confidence'), '4')
  await user.click(screen.getByRole('button', { name: 'Save completion' }))
  expect(summary().getByText('80')).toBeInTheDocument()
  expect(screen.getByRole('progressbar', { name: 'Coding session completion' })).toHaveAttribute('value', '100')
  app.unmount()
  render(<DataProvider><Dashboard onNavigate={() => {}} /></DataProvider>)
  expect(summary().getByText('80')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Undo completion' }))
  await user.click(screen.getByRole('button', { name: 'Close' }))
  expect(summary().getByText('80')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Undo completion' }))
  await user.click(screen.getByRole('button', { name: 'Clear completion' }))
  expect(summary().getByText('0')).toBeInTheDocument()
  expect(screen.getByRole('progressbar', { name: 'Coding session completion' })).toHaveAttribute('value', '0')
})
it('displays due resources even when marked reviewed', () => {
  const today = calendarDate(new Date())
  const data = applyDataAction(createEmptyData(), { type: 'addResource', input: {
    title: 'Cache notes', area: 'System Design', tags: [], source: 'Other', notes: '', status: 'Reviewed', nextRevisionDate: today,
  } })
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  render(<DataProvider><Dashboard onNavigate={() => {}} /></DataProvider>)
  expect(screen.getByText('Due today or overdue (1)')).toBeInTheDocument()
  expect(screen.getByText('Cache notes')).toBeInTheDocument()
})
