import { DataError, MAX_BACKUP_BYTES, validateBackup } from './storage'

export function downloadText(text: string, filename: string, type = 'application/json'): void {
  const url = URL.createObjectURL(new Blob([text], { type }))
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.append(link)
    try { link.click() } finally { link.remove() }
  } finally { setTimeout(() => URL.revokeObjectURL(url), 0) }
}

export async function readBackupFile(file: File) {
  if (file.size > MAX_BACKUP_BYTES) throw new DataError('size', 'Backup exceeds the 5 MiB import limit.')
  const raw = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new DataError('unavailable', 'Could not read this file. Select it again or choose another backup.'))
    reader.onabort = () => reject(new DataError('unavailable', 'File reading was cancelled. Select the backup again.'))
    reader.readAsText(file)
  })
  return validateBackup(raw)
}
