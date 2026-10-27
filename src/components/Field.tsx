import type { ReactNode } from 'react'

// Controls use id, aria-describedby={`${id}-help`} and aria-invalid when invalid.
export function Field({ id, label, hint, error, children }: {
  id: string; label: string; hint?: string; error?: string; children: ReactNode
}) {
  return <div className="field"><label htmlFor={id}>{label}</label>{children}
    {(error || hint) && <p id={`${id}-help`} className={error ? 'field-error' : 'field-hint'}>{error || hint}</p>}
  </div>
}
