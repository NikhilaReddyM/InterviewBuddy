import { PREPARATION_AREAS } from '../../types/models'
import type { AppData, StudySession } from '../../types/models'
import { addDays, getEffectiveAvailability, getWeekDates } from '../../utils/dates'

export function getTodaySessions(data: AppData, today: string): StudySession[] {
  return data.sessions.filter((session) => session.date === today).sort((a, b) =>
    Number(!!a.completion) - Number(!!b.completion) || a.topic.localeCompare(b.topic) || a.id.localeCompare(b.id))
}

function summarize(sessions: StudySession[]) {
  const completedSessions = sessions.filter((session) => session.completion).length
  return {
    plannedMinutes: sessions.reduce((sum, session) => sum + session.plannedMinutes, 0),
    completedMinutes: sessions.reduce((sum, session) => sum + (session.completion?.actualMinutes ?? 0), 0),
    scheduledSessions: sessions.length,
    completedSessions,
    completionPercent: sessions.length ? Math.round(completedSessions / sessions.length * 100) : 0,
  }
}

export function getWeeklySummary(data: AppData, weekDate: string) {
  const dates = getWeekDates(weekDate)
  const sessions = data.sessions.filter((session) => dates.includes(session.date))
  return {
    ...summarize(sessions),
    availableMinutes: dates.reduce((sum, date) => sum + getEffectiveAvailability(date, data), 0),
    weekStart: dates[0], weekEnd: dates[6],
  }
}

export function getAreaProgress(data: AppData, weekDate: string) {
  const dates = getWeekDates(weekDate)
  return PREPARATION_AREAS.map((area) => ({
    area,
    ...summarize(data.sessions.filter((session) => session.area === area && dates.includes(session.date))),
  }))
}

export function getRevisionQueue(data: AppData, today: string) {
  const end = addDays(today, 7)
  const sorted = data.resources.filter((resource) => resource.nextRevisionDate)
    .sort((a, b) => a.nextRevisionDate!.localeCompare(b.nextRevisionDate!) || a.title.localeCompare(b.title))
  return {
    due: sorted.filter((resource) => resource.nextRevisionDate! <= today),
    upcoming: sorted.filter((resource) => resource.nextRevisionDate! > today && resource.nextRevisionDate! <= end),
  }
}
