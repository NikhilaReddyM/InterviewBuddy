import type { ButtonHTMLAttributes } from 'react'

export function Button({ variant = 'primary', className = '', type = 'button', ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' }) {
  return <button type={type} className={`button button--${variant} ${className}`} {...props} />
}
