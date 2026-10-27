import { describe, expect, it } from 'vitest'
import { createEmptyChecklist, createEmptyData } from './defaults'
import {
  appDataSchema, availabilitySchema, backupSchema, calendarDateSchema,
  confidenceSchema, designAttemptSchema, durationSchema, resourceSchema,
  resourceUrlSchema, studySessionSchema,
} from './models'

const metadata = {
  id: '123e4567-e89b-42d3-a456-426614174000',
  createdAt: '2026-10-27T16:00:00Z',
  updatedAt: '2026-10-27T16:00:00Z',
}
const session = {
  ...metadata, topic: 'Cache design', area: 'System Design',
  date: '2026-10-27', plannedMinutes: 60,
}
const resource = {
  ...metadata, id: '123e4567-e89b-42d3-a456-426614174001',
  title: 'Caching notes', area: 'System Design', tags: ['cache'],
  source: 'Other', notes: '', status: 'Not Started',
}

describe('data model validation', () => {
  it('accepts the agreed empty defaults and returns independent objects', () => {
    const data = createEmptyData()
    expect(appDataSchema.parse(data)).toEqual(data)
    expect(data.preferences).toEqual({
      theme: 'light', defaultLandingScreen: 'dashboard',
      defaultWeekdayMinutes: 150, defaultWeekendMinutes: 0,
    })
    data.preferences.theme = 'dark'
    expect(createEmptyData().preferences.theme).toBe('light')
  })

  it.each(['2026-02-29', '2026-04-31', '2026-1-01', '2026-10-27T00:00:00Z'])(
    'rejects invalid calendar date %s', (date) => {
      expect(calendarDateSchema.safeParse(date).success).toBe(false)
    },
  )
  it('accepts leap days', () => {
    expect(calendarDateSchema.safeParse('2028-02-29').success).toBe(true)
  })

  it.each([0, -1, 1.5, 1441, '60', NaN, Infinity])('rejects invalid duration %s', (value) => {
    expect(durationSchema.safeParse(value).success).toBe(false)
  })
  it('allows zero availability and bounds confidence', () => {
    expect(availabilitySchema.parse(0)).toBe(0)
    expect(durationSchema.parse(1440)).toBe(1440)
    for (const value of [0, 6, 1.5]) expect(confidenceSchema.safeParse(value).success).toBe(false)
    for (const value of [1, 5]) expect(confidenceSchema.parse(value)).toBe(value)
  })

  it.each(['javascript:alert(1)', 'file:///tmp/notes', 'ftp://example.com', '/relative', ''])(
    'rejects unsafe or incomplete URL %s', (url) => {
      expect(resourceUrlSchema.safeParse(url).success).toBe(false)
    },
  )
  it('accepts HTTP and HTTPS links', () => {
    for (const url of ['https://example.com/notes', 'http://localhost:3000']) {
      expect(resourceUrlSchema.safeParse(url).success).toBe(true)
    }
  })

  it('requires actual minutes and confidence for completed sessions', () => {
    expect(studySessionSchema.safeParse(session).success).toBe(true)
    expect(studySessionSchema.safeParse({ ...session, completion: {} }).success).toBe(false)
    const completed = studySessionSchema.parse({
      ...session,
      completion: { actualMinutes: 75, takeaways: '', confidence: 3, completedAt: metadata.updatedAt },
    })
    expect(completed.completion?.actualMinutes).toBe(75)
  })

  it('rejects blank titles, unknown areas, and unexpected fields', () => {
    for (const patch of [{ topic: '  ' }, { area: 'Unknown' }, { extra: true }]) {
      expect(studySessionSchema.safeParse({ ...session, ...patch }).success).toBe(false)
    }
  })

  it('allows resources and design attempts without an initial confidence', () => {
    expect(resourceSchema.safeParse(resource).success).toBe(true)
    expect(designAttemptSchema.safeParse({
      ...metadata, title: 'URL shortener', requirementsAndAssumptions: '',
      scaleEstimates: '', apisAndDataModel: '', architectureNotes: '',
      tradeoffsAndFailureScenarios: '', missedAndNextSteps: '',
      checklist: createEmptyChecklist(),
    }).success).toBe(true)
  })

  it('rejects duplicate IDs and dangling resource references', () => {
    const data = { ...createEmptyData(), sessions: [session, session] }
    expect(appDataSchema.safeParse(data).success).toBe(false)
    const linked = { ...session, resourceId: resource.id }
    expect(appDataSchema.safeParse({ ...createEmptyData(), sessions: [linked] }).success).toBe(false)
    expect(appDataSchema.safeParse({
      ...createEmptyData(), sessions: [linked], resources: [resource],
    }).success).toBe(true)
  })

  it('validates availability override dates and schema versions', () => {
    expect(appDataSchema.safeParse({ ...createEmptyData(), schemaVersion: 99 }).success).toBe(false)
    expect(appDataSchema.safeParse({
      ...createEmptyData(), availabilityOverrides: { '2026-02-30': 150 },
    }).success).toBe(false)
  })

  it('accepts a JSON round-trip backup and rejects an invalid timestamp', () => {
    const backup = { exportedAt: metadata.updatedAt, data: createEmptyData() }
    expect(backupSchema.parse(JSON.parse(JSON.stringify(backup)))).toEqual(backup)
    expect(backupSchema.safeParse({ ...backup, exportedAt: 'yesterday' }).success).toBe(false)
  })
})
