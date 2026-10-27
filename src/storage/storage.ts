import { z } from 'zod'
import { appDataSchema, backupSchema, SCHEMA_VERSION } from '../types/models'
import type { AppData } from '../types/models'
import { createEmptyData } from '../types/defaults'

export const STORAGE_KEY = 'interview-prep-companion:v1'
export const MAX_BACKUP_BYTES = 5 * 1024 * 1024
export type StoragePort = Pick<Storage, 'getItem' | 'setItem'>
export type StorageErrorCode = 'unavailable' | 'invalid' | 'version' | 'quota' | 'conflict' | 'size'

export class DataError extends Error {
  readonly code: StorageErrorCode
  constructor(code: StorageErrorCode, message: string) {
    super(message)
    this.name = 'DataError'
    this.code = code
  }
}

export type LoadResult =
  | { status: 'empty' | 'ready'; data: AppData; raw: string | null }
  | { status: 'error'; error: DataError; raw: string | null }

// Keep the original key; old data is validated and migrated in memory before use.
const legacySchema = z.strictObject({
  ...appDataSchema.shape,
  schemaVersion: z.literal(1),
  jobApplications: z.never().optional(),
  preferences: appDataSchema.shape.preferences.extend({
    defaultLandingScreen: z.enum(['dashboard', 'planner', 'resources', 'design-lab', 'settings']),
  }),
})
export function validateData(input: unknown): AppData {
  if (input && typeof input === 'object' && 'schemaVersion' in input && input.schemaVersion === 1) {
    const legacy = legacySchema.safeParse(input)
    if (!legacy.success) throw new DataError('invalid', 'Legacy data failed validation. No saved data has been replaced.')
    input = { ...legacy.data, schemaVersion: SCHEMA_VERSION, jobApplications: [] }
  }
  if (input && typeof input === 'object' && 'schemaVersion' in input
      && input.schemaVersion !== SCHEMA_VERSION) {
    throw new DataError('version', 'This data version is unsupported. Keep a backup and open it with a compatible app version.')
  }
  const parsed = appDataSchema.safeParse(input)
  if (!parsed.success) throw new DataError('invalid', 'Data failed validation. No saved data has been replaced.')
  return parsed.data
}

function parseJson(raw: string): unknown {
  try { return JSON.parse(raw) as unknown }
  catch { throw new DataError('invalid', 'The saved value is not valid JSON. Download it before attempting recovery.') }
}

function browserStorage(): StoragePort {
  try { return window.localStorage }
  catch { throw new DataError('unavailable', 'Browser storage is unavailable. Enable storage and retry.') }
}

export function loadData(storage?: StoragePort): LoadResult {
  let raw: string | null = null
  try {
    raw = (storage ?? browserStorage()).getItem(STORAGE_KEY)
  } catch {
    return { status: 'error', raw, error: new DataError('unavailable', 'Cannot read browser storage. Enable storage and retry.') }
  }
  try {
    return raw === null
      ? { status: 'empty', raw, data: createEmptyData() }
      : { status: 'ready', raw, data: validateData(parseJson(raw)) }
  } catch (error) {
    return { status: 'error', raw, error: error as DataError }
  }
}

// Validate before writing; compare the last loaded value to avoid silent stale-tab writes.
export function saveData(input: unknown, expectedRaw: string | null, storage?: StoragePort): string {
  const data = validateData(input)
  const port = storage ?? browserStorage()
  let current: string | null
  try { current = port.getItem(STORAGE_KEY) }
  catch { throw new DataError('unavailable', 'Cannot read browser storage. Your change was not saved.') }
  if (current !== expectedRaw) {
    throw new DataError('conflict', 'Saved data changed in another tab. Reload saved data before editing again.')
  }
  const raw = JSON.stringify(data)
  try { port.setItem(STORAGE_KEY, raw) }
  catch (error) {
    if (error instanceof DOMException && (error.name === 'QuotaExceededError' || error.name === 'NS_ERROR_DOM_QUOTA_REACHED')) {
      throw new DataError('quota', 'Browser storage is full. Your change was not saved. Export a backup before freeing space.')
    }
    throw new DataError('unavailable', 'Cannot write browser storage. Your change was not saved.')
  }
  return raw
}

export function exportBackup(data: AppData): string {
  return JSON.stringify({ exportedAt: new Date().toISOString(), data: validateData(data) }, null, 2)
}

export function validateBackup(raw: string): AppData {
  if (new Blob([raw]).size > MAX_BACKUP_BYTES) {
    throw new DataError('size', 'Backup exceeds the 5 MiB import limit.')
  }
  const input = parseJson(raw)
  const normalized = input && typeof input === 'object' && 'data' in input
    ? { ...input, data: validateData(input.data) } : input
  const parsed = backupSchema.safeParse(normalized)
  if (!parsed.success) throw new DataError('invalid', 'This file is not a valid Interview Prep Companion backup.')
  return parsed.data.data
}

// Confirmation is explicit; the import screen must show a preview before calling this.
export function replaceData(input: unknown, expectedRaw: string | null, confirmed: boolean, storage?: StoragePort): string {
  if (!confirmed) throw new DataError('invalid', 'Confirm replacement before importing data.')
  return saveData(input, expectedRaw, storage)
}
