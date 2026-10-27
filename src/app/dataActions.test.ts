import { expect, it } from 'vitest'
import { applyDataAction } from './dataActions'
import { createEmptyChecklist, createEmptyData } from '../types/defaults'

it('updates and deletes resources while preserving linked session snapshots', () => {
  const input = { title: 'Notes', area: 'Coding' as const, tags: [], source: 'Other' as const,
    notes: '', status: 'Not Started' as const }
  const original = createEmptyData()
  let data = applyDataAction(original, { type: 'addResource', input: { ...input, url: 'https://example.com', nextRevisionDate: '2026-10-27' } })
  const id = data.resources[0].id
  data = applyDataAction(data, { type: 'addSession', input: {
    topic: 'Notes', area: 'Coding', date: '2026-10-27', plannedMinutes: 60,
    resourceId: id, resourceUrl: 'https://example.com',
  } })
  data = applyDataAction(data, { type: 'updateResource', id, input })
  expect(data.resources[0].url).toBeUndefined()
  expect(data.resources[0].nextRevisionDate).toBeUndefined()
  data = applyDataAction(data, { type: 'deleteResource', id })
  expect(data.sessions[0].resourceId).toBeUndefined()
  expect(data.sessions[0].resourceUrl).toBe('https://example.com')
  expect(data.sessions[0].topic).toBe('Notes')
  expect(original.resources).toHaveLength(0)
  data = applyDataAction(data, { type: 'updateSession', id: data.sessions[0].id,
    input: { topic: 'Trees', area: 'Coding', date: '2026-10-28', plannedMinutes: 45 } })
  expect(data.sessions[0].resourceUrl).toBeUndefined()
  data = applyDataAction(data, { type: 'deleteSession', id: data.sessions[0].id })
  expect(data.sessions).toHaveLength(0)
})

it('handles design attempt CRUD and availability overrides', () => {
  const input = { title: 'Chat', requirementsAndAssumptions: '', scaleEstimates: '',
    apisAndDataModel: '', architectureNotes: '', tradeoffsAndFailureScenarios: '',
    missedAndNextSteps: '', checklist: createEmptyChecklist() }
  let data = applyDataAction(createEmptyData(), { type: 'addDesignAttempt', input })
  const id = data.designAttempts[0].id
  data = applyDataAction(data, { type: 'updateDesignAttempt', id, input: { ...input, title: 'Search' } })
  expect(data.designAttempts[0].title).toBe('Search')
  data = applyDataAction(data, { type: 'deleteDesignAttempt', id })
  expect(data.designAttempts).toHaveLength(0)
  data = applyDataAction(data, { type: 'setAvailability', date: '2026-10-27', minutes: 0 })
  expect(data.availabilityOverrides['2026-10-27']).toBe(0)
  data = applyDataAction(data, { type: 'setAvailability', date: '2026-10-27', minutes: null })
  expect(data.availabilityOverrides).toEqual({})
  expect(() => applyDataAction(data, { type: 'deleteSession', id })).toThrow('no longer exists')
})
