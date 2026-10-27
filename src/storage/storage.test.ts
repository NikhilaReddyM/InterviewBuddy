import { describe, expect, it } from 'vitest'
import { createEmptyData } from '../types/defaults'
import { exportBackup, loadData, MAX_BACKUP_BYTES, replaceData, saveData, STORAGE_KEY, validateBackup } from './storage'
import type { StoragePort } from './storage'

function memory(raw: string | null = null): StoragePort {
  return { getItem: () => raw, setItem: (_key, value) => { raw = value } }
}

describe('storage', () => {
  it('loads first-visit defaults without writing', () => {
    const port = memory()
    expect(loadData(port).status).toBe('empty')
    expect(port.getItem(STORAGE_KEY)).toBeNull()
  })
  it('persists and reloads a validated dataset', () => {
    const port = memory()
    const data = createEmptyData()
    data.preferences.theme = 'dark'
    const raw = saveData(data, null, port)
    expect(loadData(port)).toEqual({ status: 'ready', raw, data })
  })
  it.each(['{broken', '{}', '{"schemaVersion":99}'])('preserves invalid saved data: %s', (raw) => {
    const port = memory(raw)
    expect(loadData(port)).toMatchObject({ status: 'error', raw })
    expect(port.getItem(STORAGE_KEY)).toBe(raw)
  })
  it('handles inaccessible storage', () => {
    const port: StoragePort = { getItem: () => { throw new Error('blocked') }, setItem: () => {} }
    expect(loadData(port)).toMatchObject({ status: 'error', error: { code: 'unavailable' } })
    expect(() => saveData(createEmptyData(), null, port)).toThrow('Cannot read')
  })
  it('reports quota failures without changing the saved value', () => {
    const port: StoragePort = { getItem: () => null, setItem: () => { throw new DOMException('full', 'QuotaExceededError') } }
    expect(() => saveData(createEmptyData(), null, port)).toThrow('storage is full')
    expect(port.getItem(STORAGE_KEY)).toBeNull()
  })
  it('rejects stale writes from another tab', () => {
    const port = memory()
    const raw = saveData(createEmptyData(), null, port)
    expect(() => saveData(createEmptyData(), null, port)).toThrow('another tab')
    expect(port.getItem(STORAGE_KEY)).toBe(raw)
  })
  it('requires confirmation and validates before replacement', () => {
    const port = memory('broken')
    expect(() => replaceData(createEmptyData(), 'broken', false, port)).toThrow('Confirm')
    expect(() => replaceData({}, 'broken', true, port)).toThrow('validation')
    expect(port.getItem(STORAGE_KEY)).toBe('broken')
    replaceData(createEmptyData(), 'broken', true, port)
    expect(loadData(port).status).toBe('ready')
  })
  it('round-trips backups without writing and rejects invalid envelopes', () => {
    const data = createEmptyData()
    expect(validateBackup(exportBackup(data))).toEqual(data)
    for (const raw of ['invalid', '{}', JSON.stringify({ exportedAt: 'wrong', data })]) {
      expect(() => validateBackup(raw)).toThrow()
    }
  })
  it('rejects oversized backup strings', () => {
    expect(() => validateBackup('a'.repeat(MAX_BACKUP_BYTES + 1))).toThrow('5 MiB')
  })
})
