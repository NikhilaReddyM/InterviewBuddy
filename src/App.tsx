import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, BriefcaseBusiness, BookOpen, CalendarDays, FlaskConical, GraduationCap, LayoutDashboard, Moon, Settings, Sun } from 'lucide-react'
import type { Screen } from './types/models'
import { useAppData } from './app/dataContext'
import { Button } from './components/Button'
import { Field } from './components/Field'
import { Dialog } from './components/Dialog'
import './App.css'
import { JobApplications } from './features/jobs/JobApplications'
import { BackupControls } from './features/settings/BackupControls'
import { downloadText } from './storage/files'
import { Dashboard } from './features/dashboard/Dashboard'
import { SystemDesignLab } from './features/design-lab/SystemDesignLab'
import { ResourceLibrary } from './features/resources/ResourceLibrary'
import { Opportunities } from './features/opportunities/Opportunities'
import { ApplicationWorkspaces } from './features/workspaces/ApplicationWorkspaces'
import { CareerProfile } from './features/career-profile/CareerProfile'
import { WeeklyPlanner } from './features/planner/WeeklyPlanner'

const sections = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, description: 'A little progress, every day.' },
  { id: 'planner', label: 'Weekly Planner', icon: CalendarDays, description: 'Make room for focused preparation.' },
  { id: 'resources', label: 'Resources & Revision', icon: BookOpen, description: 'Keep useful material close, and revisit what matters.' },
  { id: 'design-lab', label: 'System Design Lab', icon: FlaskConical, description: 'Practice your reasoning, one design at a time.' },
  { id: 'jobs', label: 'Job Applications', icon: BriefcaseBusiness, description: 'Track your applications and keep your next steps in view.' },
  { id: 'career-profile', label: 'Career Profile', icon: BriefcaseBusiness, description: 'Upload your resume and inspect the extracted text.' },
  { id: 'opportunities', label: 'Find Opportunities', icon: BriefcaseBusiness, description: 'Discover matching jobs and review prepared applications.' },
  { id: 'workspaces', label: 'Application Workspaces', icon: BriefcaseBusiness, description: 'Keep job descriptions, application drafts, and reviews together.' },
  { id: 'settings', label: 'Settings & Backup', icon: Settings, description: 'Make this space your own.' },
] as const

function App() {
  const { data, error, blocked, rawRecovery, reload, dispatch } = useAppData()
  const [navigation, setNavigation] = useState<Screen[]>([data.preferences.defaultLandingScreen])
  const screen = navigation[navigation.length - 1]
  const previousScreen = navigation.length > 1 ? navigation[navigation.length - 2] : undefined
  const previousLabel = sections.find((item) => item.id === previousScreen)?.label
  const [targetWorkspace, setTargetWorkspace] = useState<string | undefined>(undefined)
  const [storageInfo, setStorageInfo] = useState(false)
  const [notice, setNotice] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const section = sections.find((item) => item.id === screen)!
  const dark = data.preferences.theme === 'dark'
  useEffect(() => {
    document.documentElement.dataset.theme = data.preferences.theme
  }, [data.preferences.theme])
  useEffect(() => { document.title = `${section.label} · Interview Prep Companion` }, [section.label])

  function navigate(next: Screen) {
    if (!window.dispatchEvent(new Event('interviewbuddy:before-navigate', { cancelable: true }))) return
    setNavigation((history) => history[history.length - 1] === next ? history : [...history, next])
    requestAnimationFrame(() => heading.current?.focus())
  }
  function goBack() {
    if (!window.dispatchEvent(new Event('interviewbuddy:before-navigate', { cancelable: true }))) return
    setNavigation((history) => history.length > 1 ? history.slice(0, -1) : history)
    requestAnimationFrame(() => heading.current?.focus())
  }
  function downloadRecovery() {
    if (rawRecovery === null) return
    try { downloadText(rawRecovery, 'interview-prep-recovery.txt', 'text/plain') }
    catch { setNotice('Recovery download failed. Your saved data has not changed.') }
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar">
      <div className="brand"><GraduationCap size={30} aria-hidden="true" /><div>Interview Prep<span>COMPANION</span></div></div>
      <p className="nav-caption">YOUR PREPARATION</p>
      <nav aria-label="Main navigation">{sections.map(({ id, label, icon: Icon }) =>
        <button key={id} type="button" className={`nav-item ${screen === id ? 'active' : ''}`}
          aria-current={screen === id ? 'page' : undefined} onClick={() => navigate(id)}>
          <Icon size={20} aria-hidden="true" /><span>{label}</span>
        </button>)}</nav>
      <div className="sidebar-footer"><span className="local-dot" />Personal workspace<span className="local-caption">Stored in this browser</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>Small steps. Strong foundations.</span>
        <Button variant="secondary" disabled={blocked} onClick={() => {
          if (dispatch({ type: 'updatePreferences', input: { theme: dark ? 'light' : 'dark' } })) setNotice('Theme saved.')
        }} aria-label={`Switch to ${dark ? 'light' : 'dark'} theme`}>
          {dark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}<span>{dark ? 'Light' : 'Dark'} theme</span>
        </Button>
      </header>
      <main id="main-content" tabIndex={-1}>
        <div className="page-heading">{previousScreen && <Button variant="secondary" className="back-navigation" disabled={!previousScreen} onClick={goBack}
          aria-label={previousLabel ? `Back to ${previousLabel}` : 'Back — no previous section'}>
          <ArrowLeft size={17} aria-hidden="true" />{previousLabel ? `Back to ${previousLabel}` : 'Back'}
        </Button>}<p className="eyebrow">INTERVIEW PREP COMPANION</p><h1 ref={heading} tabIndex={-1}>{section.label}</h1><p>{section.description}</p></div>
        {error && <section className="error-banner" role="alert"><h2>Storage needs attention</h2><p>{error}</p><div className="actions">
          <Button variant="secondary" onClick={reload}>Reload saved data</Button>
          {rawRecovery !== null && <Button variant="secondary" onClick={downloadRecovery}>Download saved value for recovery</Button>}
          <Button variant="secondary" onClick={() => navigate('settings')}>Open backup & recovery</Button>
        </div></section>}
        <p className="sr-only" role="status">{notice}</p>
        {screen === 'dashboard' ? <Dashboard onNavigate={navigate} /> : screen === 'planner' ? <WeeklyPlanner /> : screen === 'resources' ? <ResourceLibrary /> : screen === 'design-lab' ? <SystemDesignLab /> : screen === 'jobs' ? <JobApplications /> : screen === 'career-profile' ? <CareerProfile /> : screen === 'workspaces' ? <ApplicationWorkspaces initialWorkspaceId={targetWorkspace} /> : screen === 'opportunities' ? <Opportunities onOpenWorkspace={workspaceId => { setTargetWorkspace(workspaceId); navigate('workspaces') }} /> : screen === 'settings' ? <div className="settings-grid">
          <section className="card settings-card"><h2>Preferences</h2><p>Your choices are saved in this browser.</p>
            <Field id="landing-screen" label="Start on" hint="Choose the first screen shown when you reopen the app.">
              <select id="landing-screen" aria-describedby="landing-screen-help" value={data.preferences.defaultLandingScreen} disabled={blocked} onChange={(event) => {
                if (dispatch({ type: 'updatePreferences', input: { defaultLandingScreen: event.target.value as Screen } })) setNotice('Default screen saved.')
              }}>{sections.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
            </Field><p className="subtle">Study availability starts at 150 minutes on weekdays and 0 on weekends. Edit individual days in the Weekly Planner.</p>
          </section>
          <section className="card settings-card"><h2>Browser storage</h2><p>Your data stays in this browser. Export regular backups before clearing browser data or moving to another device.</p><Button variant="secondary" onClick={() => setStorageInfo(true)}>About local storage</Button></section>
          <BackupControls />
        </div> : null}
      </main>
    </div>
    {storageInfo && <Dialog title="About local storage" onClose={() => setStorageInfo(false)}><p>Data is saved only in this browser and for this app address. It does not sync across devices. Clearing browser data can remove it.</p><p>Storage has limited capacity and is not encrypted. Keep passwords, API keys, and confidential work material elsewhere.</p></Dialog>}
  </div>
}
export default App
