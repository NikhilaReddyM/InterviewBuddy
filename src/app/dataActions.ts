import type { AppData, StudySession, Resource, DesignAttempt, SessionCompletion, Preferences, JobApplication } from '../types/models'
import { validateData } from '../storage/storage'

type Fields<T> = Omit<T, 'id' | 'createdAt' | 'updatedAt'>
export type SessionInput = Omit<Fields<StudySession>, 'completion'>
export type ResourceInput = Fields<Resource>
export type JobApplicationInput = Fields<JobApplication>
export type DesignAttemptInput = Fields<DesignAttempt>

export type DataAction =
  | { type: 'addJobApplication'; input: JobApplicationInput }
  | { type: 'updateJobApplication'; id: string; input: JobApplicationInput }
  | { type: 'deleteJobApplication' | 'completeApplicationReminder'; id: string }
  | { type: 'addSession'; input: SessionInput }
  | { type: 'updateSession'; id: string; input: SessionInput }
  | { type: 'deleteSession' | 'undoCompletion'; id: string }
  | { type: 'completeSession'; id: string; input: Omit<SessionCompletion, 'completedAt'> }
  | { type: 'addResource'; input: ResourceInput }
  | { type: 'updateResource'; id: string; input: ResourceInput }
  | { type: 'deleteResource'; id: string }
  | { type: 'addDesignAttempt'; input: DesignAttemptInput }
  | { type: 'updateDesignAttempt'; id: string; input: DesignAttemptInput }
  | { type: 'deleteDesignAttempt'; id: string }
  | { type: 'setAvailability'; date: string; minutes: number | null }
  | { type: 'updatePreferences'; input: Partial<Preferences> }

export function applyDataAction(data: AppData, action: DataAction): AppData {
  const next = structuredClone(data)
  const now = new Date().toISOString()
  const metadata = () => ({ id: crypto.randomUUID(), createdAt: now, updatedAt: now })
  function find<T extends { id: string }>(records: T[], id: string): T {
    const record = records.find((item) => item.id === id)
    if (!record) throw new Error('This record no longer exists. Reload saved data and retry.')
    return record
  }
  switch (action.type) {
    case 'addJobApplication': next.jobApplications.push({ ...action.input, ...metadata() }); break
    case 'updateJobApplication': {
      const existing = find(next.jobApplications, action.id)
      next.jobApplications[next.jobApplications.indexOf(existing)] = {
        ...action.input, id: existing.id, createdAt: existing.createdAt, updatedAt: now,
        // Keep the historical submission date when changing status later.
        applicationDate: action.input.applicationDate ?? existing.applicationDate,
      }
      break
    }
    case 'deleteJobApplication':
      find(next.jobApplications, action.id)
      next.jobApplications = next.jobApplications.filter((job) => job.id !== action.id)
      break
    case 'completeApplicationReminder': {
      const job = find(next.jobApplications, action.id)
      delete job.nextAction
      delete job.reminderDate
      job.updatedAt = now
      break
    }
    case 'addSession': next.sessions.push({ ...action.input, ...metadata() }); break
    case 'updateSession': {
      const existing = find(next.sessions, action.id)
      next.sessions[next.sessions.indexOf(existing)] = {
        ...action.input, id: existing.id, createdAt: existing.createdAt, updatedAt: now,
        ...(existing.completion ? { completion: existing.completion } : {}),
      }
      break
    }
    case 'completeSession': Object.assign(find(next.sessions, action.id), {
      completion: { ...action.input, completedAt: now }, updatedAt: now,
    }); break
    case 'undoCompletion': {
      const session = find(next.sessions, action.id)
      delete session.completion
      session.updatedAt = now
      break
    }
    case 'deleteSession':
      find(next.sessions, action.id)
      next.sessions = next.sessions.filter((item) => item.id !== action.id)
      break
    case 'addResource': next.resources.push({ ...action.input, ...metadata() }); break
    case 'updateResource': {
      const existing = find(next.resources, action.id)
      next.resources[next.resources.indexOf(existing)] = {
        ...action.input, id: existing.id, createdAt: existing.createdAt, updatedAt: now,
      }
      break
    }
    case 'deleteResource':
      find(next.resources, action.id)
      next.resources = next.resources.filter((item) => item.id !== action.id)
      for (const session of next.sessions) {
        if (session.resourceId === action.id) {
          delete session.resourceId
          session.updatedAt = now
        }
      }
      break
    case 'addDesignAttempt': next.designAttempts.push({ ...action.input, ...metadata() }); break
    case 'updateDesignAttempt': {
      const existing = find(next.designAttempts, action.id)
      next.designAttempts[next.designAttempts.indexOf(existing)] = {
        ...action.input, id: existing.id, createdAt: existing.createdAt, updatedAt: now,
      }
      break
    }
    case 'deleteDesignAttempt':
      find(next.designAttempts, action.id)
      next.designAttempts = next.designAttempts.filter((item) => item.id !== action.id)
      break
    case 'setAvailability':
      if (action.minutes === null) delete next.availabilityOverrides[action.date]
      else next.availabilityOverrides[action.date] = action.minutes
      break
    case 'updatePreferences': Object.assign(next.preferences, action.input); break
  }
  return validateData(next)
}
