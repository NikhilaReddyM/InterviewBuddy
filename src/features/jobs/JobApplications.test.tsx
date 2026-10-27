import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { DataProvider } from '../../app/DataProvider'
import { loadData } from '../../storage/storage'
import { calendarDate, addDays } from '../../utils/dates'
import { JobApplications } from './JobApplications'
import { ApplicationReminders } from './ApplicationReminders'

beforeEach(() => {
  localStorage.clear()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
const renderJobs = () => render(<DataProvider><JobApplications /></DataProvider>)
function savedJobs() {
  const result = loadData()
  if (result.status === 'error') throw result.error
  return result.data.jobApplications
}
async function addJob() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Add application' }))
  await user.type(screen.getByLabelText('Company'), 'Acme')
  await user.type(screen.getByLabelText('Role'), 'Staff Engineer')
  await user.type(screen.getByLabelText('Job URL (optional)'), 'https://example.com/job')
  await user.type(screen.getByLabelText('Next action (optional)'), 'Finish application')
  fireEvent.change(screen.getByLabelText('Reminder date (optional)'), { target: { value: calendarDate(new Date()) } })
  await user.click(screen.getByRole('button', { name: 'Save application' }))
}
it('creates, submits, edits, persists, filters and deletes an application', async () => {
  const user = userEvent.setup()
  const app = renderJobs()
  await addJob()
  expect(savedJobs()[0].status).toBe('Saved')
  await user.click(screen.getByRole('button', { name: 'Edit application / reminder' }))
  await user.selectOptions(screen.getByLabelText('Application status'), 'Applied')
  await user.click(screen.getByRole('button', { name: 'Save application' }))
  expect(screen.getByLabelText('Application date')).toHaveAttribute('aria-invalid', 'true')
  fireEvent.change(screen.getByLabelText('Application date'), { target: { value: calendarDate(new Date()) } })
  await user.click(screen.getByRole('button', { name: 'Save application' }))
  const summary = within(screen.getByRole('region', { name: 'Application summary' }))
  expect(summary.getAllByText('1')).toHaveLength(3)
  expect(screen.getByRole('link', { name: 'Open application page ↗' })).toHaveAttribute('rel', 'noopener noreferrer')
  app.unmount()
  renderJobs()
  expect(savedJobs()[0].status).toBe('Applied')
  await user.type(screen.getByLabelText('Search applications'), 'staff')
  expect(screen.getByRole('article', { name: 'Acme · Staff Engineer' })).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Filter application status'), 'Rejected')
  expect(screen.getByText('No matching applications')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Reset application filters' }))
  await user.click(screen.getByLabelText('Due reminders only'))
  expect(screen.getByRole('article')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Delete application' }))
  await user.click(screen.getByRole('button', { name: 'Close' }))
  expect(savedJobs()).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'Delete application' }))
  await user.click(screen.getByRole('button', { name: 'Delete permanently' }))
  expect(savedJobs()).toHaveLength(0)
})
it('reschedules and completes reminders on the Dashboard without changing application status', async () => {
  const user = userEvent.setup()
  const app = renderJobs()
  await addJob()
  app.unmount()
  render(<DataProvider><ApplicationReminders /></DataProvider>)
  expect(screen.getByText('Due today or overdue (1)')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Open application / reschedule' }))
  fireEvent.change(screen.getByLabelText('Reminder date (optional)'), { target: { value: addDays(calendarDate(new Date()), 1) } })
  await user.click(screen.getByRole('button', { name: 'Save application' }))
  expect(screen.getByText('Next 7 days (1)')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Mark reminder done' }))
  expect(savedJobs()[0].reminderDate).toBeUndefined()
  expect(savedJobs()[0].status).toBe('Saved')
  expect(screen.getByText('Next 7 days (0)')).toBeInTheDocument()
})
it('validates and protects unsaved changes and retains inputs on storage failure', async () => {
  const user = userEvent.setup()
  renderJobs()
  await user.click(screen.getByRole('button', { name: 'Add application' }))
  await user.click(screen.getByRole('button', { name: 'Save application' }))
  expect(screen.getByLabelText('Company')).toHaveAttribute('aria-invalid', 'true')
  await user.type(screen.getByLabelText('Company'), 'Beta')
  await user.type(screen.getByLabelText('Role'), 'Senior Engineer')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  await user.click(screen.getByRole('button', { name: 'Keep editing' }))
  expect(screen.getByLabelText('Company')).toHaveValue('Beta')
  const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError') })
  try {
    await user.click(screen.getByRole('button', { name: 'Save application' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save')
    expect(savedJobs()).toHaveLength(0)
  } finally { spy.mockRestore() }
  await user.click(screen.getByRole('button', { name: 'Save application' }))
  expect(savedJobs()).toHaveLength(1)
})
