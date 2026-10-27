import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { Button } from './Button'

// Native modal supplies focus containment, Escape handling, and focus restoration.
export function Dialog({ title, children, onClose, closeLabel = 'Close' }: {
  title: string; children: ReactNode; onClose: () => void; closeLabel?: string
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const dialog = ref.current!
    dialog.showModal()
    return () => dialog.close()
  }, [])
  return <dialog ref={ref} aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); onClose() }}>
    <h2 id={titleId}>{title}</h2>{children}
    <div className="dialog-actions"><Button variant="secondary" onClick={onClose}>{closeLabel}</Button></div>
  </dialog>
}

export function ConfirmDialog({ title, children, confirmLabel = 'Confirm', onConfirm, onClose }: {
  title: string; children: ReactNode; confirmLabel?: string; onConfirm: () => void; onClose: () => void
}) {
  return <Dialog title={title} onClose={onClose}>{children}
    <Button variant="danger" onClick={onConfirm}>{confirmLabel}</Button>
  </Dialog>
}
