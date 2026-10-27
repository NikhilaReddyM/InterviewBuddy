import { describe, expect, it } from 'vitest'
import { createEmptyData } from '../../types/defaults'
import type { StudySession } from '../../types/models'
import { applyDataAction } from '../../app/dataActions'
import { getAreaProgress, getRevisionQueue, getTodaySessions, getWeeklySummary } from './calculations'

const today = '2026-10-27'
function session(id: string, date: string, plannedMinutes: number, actualMinutes?: number): StudySession {
  return { id, date, topic: id, area: 'Coding', plannedMinutes, createdAt: '', updatedAt: '',
    ...(actualMinutes ? { completion: { actualMinutes, confidence: 3, takeaways: '', completedAt: '2026-11-10T00:00:00Z' } } : {}) }
}
describe('dashboard calculations', () => {
  it('handles empty data without NaN and includes all seven areas', () => {
    const data = createEmptyData()
    expect(getWeeklySummary(data, today)).toMatchObject({ plannedMinutes: 0, completedMinutes: 0, scheduledSessions: 0, completedSessions: 0, completionPercent: 0, availableMinutes: 750 })
    expect(getAreaProgress(data, today)).toHaveLength(7)
    expect(getAreaProgress(data, today).every((area) => area.completionPercent === 0)).toBe(true)
    expect(getTodaySessions(data, today)).toEqual([])
    expect(getRevisionQueue(data, today)).toEqual({ due: [], upcoming: [] })
  })
  it('counts scheduled dates within Monday–Sunday, actual overrun, and availability overrides', () => {
    const data = createEmptyData()
    data.sessions = [session('mon', '2026-10-26', 60, 90), session('today', today, 30), session('sun', '2026-11-01', 45, 20), session('previous', '2026-10-25', 100, 100), session('next', '2026-11-02', 100, 100)]
    data.availabilityOverrides[today] = 0
    data.availabilityOverrides['2026-11-01'] = 60
    expect(getWeeklySummary(data, today)).toEqual({ plannedMinutes: 135, completedMinutes: 110, scheduledSessions: 3, completedSessions: 2, completionPercent: 67, availableMinutes: 660, weekStart: '2026-10-26', weekEnd: '2026-11-01' })
    const area = getAreaProgress(data, today)[0]
    expect(area).toMatchObject({ plannedMinutes: 135, completedMinutes: 110, completedSessions: 2 })
    expect(getAreaProgress(data, today)[1].scheduledSessions).toBe(0)
  })
  it('orders only today’s sessions with incomplete sessions first without mutating input', () => {
    const data = createEmptyData()
    data.sessions = [session('Z', today, 10, 10), session('B', today, 10), session('A', today, 10), session('yesterday', '2026-10-26', 10)]
    expect(getTodaySessions(data, today).map((s) => s.id)).toEqual(['A', 'B', 'Z'])
    expect(data.sessions[0].id).toBe('Z')
  })
  it('groups overdue and today before upcoming dates through day seven, regardless of resource status', () => {
    const data = createEmptyData()
    for (const [index, date] of [undefined, '2026-10-20', today, '2026-11-03', '2026-11-04'].entries()) {
      data.resources.push({ id: String(index), title: String(index), area: 'Coding', tags: [], source: 'Other', notes: '', status: 'Reviewed', nextRevisionDate: date, createdAt: '', updatedAt: '' })
    }
    expect(getRevisionQueue(data, today).due.map((r) => r.id)).toEqual(['1', '2'])
    expect(getRevisionQueue(data, today).upcoming.map((r) => r.id)).toEqual(['3'])
  })
  it('reflects completion, undo, moving dates, and deleting sessions immediately', () => {
    let data = applyDataAction(createEmptyData(), { type: 'addSession', input: { topic: 'Trees', area: 'Coding', date: today, plannedMinutes: 30 } })
    const id = data.sessions[0].id
    data = applyDataAction(data, { type: 'completeSession', id, input: { actualMinutes: 45, confidence: 4, takeaways: '' } })
    expect(getWeeklySummary(data, today).completedMinutes).toBe(45)
    expect(getAreaProgress(data, today)[0].completionPercent).toBe(100)
    data = applyDataAction(data, { type: 'undoCompletion', id })
    expect(getWeeklySummary(data, today).completedMinutes).toBe(0)
    expect(getWeeklySummary(data, today).plannedMinutes).toBe(30)
    data = applyDataAction(data, { type: 'updateSession', id, input: { topic: 'Trees', area: 'Coding', date: '2026-11-02', plannedMinutes: 30 } })
    expect(getWeeklySummary(data, today).scheduledSessions).toBe(0)
    data = applyDataAction(data, { type: 'deleteSession', id })
    expect(getWeeklySummary(data, '2026-11-02').scheduledSessions).toBe(0)
  })
})
