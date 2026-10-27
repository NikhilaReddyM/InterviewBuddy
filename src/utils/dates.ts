import type { AppData, StudySession } from '../types/models'

export function calendarDate(date: Date): string {
  return `${date.getFullYear().toString().padStart(4, '0')}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
export function localDate(date: string): Date {
  const [year, month, day] = date.split('-').map(Number)
  const result = new Date(0)
  result.setFullYear(year, month - 1, day)
  result.setHours(12, 0, 0, 0)
  return result
}
export function addDays(date: string, days: number): string {
  const result = localDate(date)
  result.setDate(result.getDate() + days)
  return calendarDate(result)
}
export function getWeekStart(date: string): string {
  return addDays(date, -((localDate(date).getDay() + 6) % 7))
}
export function getWeekDates(date: string): string[] {
  const start = getWeekStart(date)
  return Array.from({ length: 7 }, (_, index) => addDays(start, index))
}
export function getEffectiveAvailability(date: string, data: AppData): number {
  const day = localDate(date).getDay()
  return data.availabilityOverrides[date] ?? (day === 0 || day === 6
    ? data.preferences.defaultWeekendMinutes : data.preferences.defaultWeekdayMinutes)
}
export function getDailyPlannedMinutes(date: string, sessions: StudySession[]): number {
  return sessions.filter((session) => session.date === date).reduce((sum, session) => sum + session.plannedMinutes, 0)
}
