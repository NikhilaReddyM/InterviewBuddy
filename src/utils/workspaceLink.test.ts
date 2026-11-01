import { expect, it } from 'vitest'
import { workspaceFromSearch, discoveryFromSearch } from './workspaceLink'
it('opens only valid workspace IDs from email links', () => {
  const id = '2a610ce6-60b4-46f3-ae66-5b3659ecc14e'
  expect(workspaceFromSearch(`?workspace_id=${id}`)).toBe(id)
  expect(workspaceFromSearch('?workspace_id=../../other')).toBeUndefined()
  expect(workspaceFromSearch('')).toBeUndefined()
})

it('validates discovery links independently from workspace links', () => {
  const id = '2a610ce6-60b4-46f3-ae66-5b3659ecc14e'
  expect(discoveryFromSearch(`?discovery_batch_id=${id}`)).toBe(id)
  expect(discoveryFromSearch('?discovery_batch_id=../../other')).toBeUndefined()
  expect(discoveryFromSearch(`?workspace_id=${id}`)).toBeUndefined()
})
