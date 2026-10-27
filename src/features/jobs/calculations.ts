import type { JobApplication } from '../../types/models'
import { addDays, getWeekStart } from '../../utils/dates'

export function getApplicationSummary(jobs: JobApplication[], today: string) {
  const start = getWeekStart(today)
  const submitted = jobs.filter((job) => job.applicationDate && job.applicationDate <= today)
  return {
    week: submitted.filter((job) => job.applicationDate! >= start).length,
    month: submitted.filter((job) => job.applicationDate!.slice(0, 7) === today.slice(0, 7)).length,
    total: submitted.length,
    unfinished: jobs.filter((job) => ['Saved', 'In Progress'].includes(job.status)).length,
    interviewing: jobs.filter((job) => job.status === 'Interviewing').length,
  }
}
export function getApplicationReminders(jobs: JobApplication[], today: string) {
  const sorted = jobs.filter((job) => job.reminderDate).sort((a, b) => a.reminderDate!.localeCompare(b.reminderDate!) || a.company.localeCompare(b.company))
  return {
    due: sorted.filter((job) => job.reminderDate! <= today),
    upcoming: sorted.filter((job) => job.reminderDate! > today && job.reminderDate! <= addDays(today, 7)),
  }
}
