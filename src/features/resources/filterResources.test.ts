import { expect, it } from 'vitest'
import { emptyFilters, filterResources } from './filterResources'
import type { Resource } from '../../types/models'

const resources: Resource[] = [
  { id: 'a', title: 'Zoo', area: 'Coding', tags: ['DFS'], source: 'LeetCode', notes: 'Traversal', status: 'Reviewed', nextRevisionDate: '2026-10-26', createdAt: '', updatedAt: '2026-10-25T00:00:00Z' },
  { id: 'b', title: 'Architecture', area: 'System Design', tags: [], source: 'Other', notes: 'CAP theorem', status: 'In Progress', nextRevisionDate: '2026-10-27', createdAt: '', updatedAt: '2026-10-27T00:00:00Z' },
  { id: 'c', title: 'Cache', area: 'System Design', tags: [], source: 'Other', notes: '', status: 'Not Started', nextRevisionDate: '2026-10-28', createdAt: '', updatedAt: '2026-10-26T00:00:00Z' },
  { id: 'd', title: 'No date', area: 'Coding', tags: [], source: 'Other', notes: '', status: 'Not Started', createdAt: '', updatedAt: '2026-10-24T00:00:00Z' },
]
const ids = (filters: Partial<typeof emptyFilters>) => filterResources(resources, { ...emptyFilters, ...filters }, '2026-10-27').map((r) => r.id)
it('searches case-insensitively across title, tags, and notes', () => {
  expect(ids({ search: ' zoo ' })).toEqual(['a'])
  expect(ids({ search: 'dfs' })).toEqual(['a'])
  expect(ids({ search: 'cap theorem' })).toEqual(['b'])
})
it('combines filters and handles revision boundaries', () => {
  expect(ids({ area: 'Coding', source: 'LeetCode', status: 'Reviewed', revision: 'due' })).toEqual(['a'])
  expect(ids({ revision: 'due' })).toEqual(['b', 'a'])
  expect(ids({ revision: 'upcoming' })).toEqual(['c'])
  expect(ids({ revision: 'unscheduled' })).toEqual(['d'])
  expect(ids({ area: 'System Design', source: 'LeetCode' })).toEqual([])
})
it('sorts without mutating saved resource order and puts undated revisions last', () => {
  expect(ids({ sort: 'updated' })).toEqual(['b', 'c', 'a', 'd'])
  expect(ids({ sort: 'title' })).toEqual(['b', 'c', 'd', 'a'])
  expect(ids({ sort: 'revision' })).toEqual(['a', 'b', 'c', 'd'])
  expect(resources.map((r) => r.id)).toEqual(['a', 'b', 'c', 'd'])
})
