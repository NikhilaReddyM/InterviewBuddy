import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { DataProvider } from './app/DataProvider'
import { createEmptyData } from './types/defaults'
import { loadData, STORAGE_KEY } from './storage/storage'

function renderApp() { return render(<DataProvider><App /></DataProvider>) }
beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 0 })
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { vi.unstubAllGlobals() })

describe('application shell', () => {
  it('opens Dashboard and navigates to every screen with focus and current-page state', async () => {
    const user = userEvent.setup()
    renderApp()
    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    for (const name of ['Weekly Planner', 'Resources & Revision', 'System Design Lab', 'Job Applications', 'Settings & Backup', 'Dashboard']) {
      const nav = screen.getByRole('button', { name })
      await user.click(nav)
      expect(nav).toHaveAttribute('aria-current', 'page')
      expect(screen.getByRole('heading', { level: 1, name })).toHaveFocus()
      expect(document.title).toContain(name)
    }
  })
  it('goes back through visited sections without duplicate entries or browser navigation', async () => {
    const user = userEvent.setup()
    const browserBack = vi.spyOn(window.history, 'back')
    const app = renderApp()
    expect(screen.queryByRole('button', { name: /^Back(?: to |$)/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open weekly planner' }))
    await user.click(screen.getByRole('button', { name: 'Weekly Planner' }))
    await user.click(screen.getByRole('button', { name: 'Resources & Revision' }))
    await user.click(screen.getByRole('button', { name: 'Back to Weekly Planner' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Weekly Planner' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Back to Dashboard' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toHaveFocus()
    expect(screen.queryByRole('button', { name: /^Back(?: to |$)/ })).not.toBeInTheDocument()
    expect(browserBack).not.toHaveBeenCalled()
    browserBack.mockRestore()
    app.unmount()
    renderApp()
    expect(screen.queryByRole('button', { name: /^Back(?: to |$)/ })).not.toBeInTheDocument()
  })
  it('saves the theme and restores it after remount', async () => {
    const user = userEvent.setup()
    const app = renderApp()
    await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    const saved = loadData()
    expect(saved.status !== 'error' && saved.data.preferences.theme).toBe('dark')
    app.unmount()
    renderApp()
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
  it('saves a different landing screen without unexpectedly navigating', async () => {
    const user = userEvent.setup()
    const app = renderApp()
    await user.click(screen.getByRole('button', { name: 'Settings & Backup' }))
    await user.selectOptions(screen.getByLabelText('Start on'), 'resources')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Settings & Backup')
    app.unmount()
    renderApp()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Resources & Revision')
  })
  it('opens and closes the labeled storage information dialog, including cancel', async () => {
    const user = userEvent.setup()
    renderApp()
    await user.click(screen.getByRole('button', { name: 'Settings & Backup' }))
    await user.click(screen.getByRole('button', { name: 'About local storage' }))
    expect(screen.getByRole('dialog', { name: 'About local storage' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'About local storage' }))
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('preserves recovery controls and keeps blocked preferences disabled', async () => {
    localStorage.setItem(STORAGE_KEY, 'broken')
    const user = userEvent.setup()
    renderApp()
    expect(screen.getByRole('alert')).toHaveTextContent('not valid JSON')
    expect(screen.getByRole('button', { name: 'Download saved value for recovery' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeDisabled()
    localStorage.setItem(STORAGE_KEY, JSON.stringify(createEmptyData()))
    await user.click(screen.getByRole('button', { name: 'Reload saved data' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeEnabled()
  })
  it('supports keyboard activation of navigation', async () => {
    const user = userEvent.setup()
    renderApp()
    screen.getByRole('button', { name: 'Weekly Planner' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('heading', { level: 1, name: 'Weekly Planner' })).toHaveFocus()
  })
})
