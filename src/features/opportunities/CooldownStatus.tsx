import { useEffect, useState } from 'react'
import { remainingCooldown } from './cooldown'


export function CooldownStatus({ until, serverTime }: { until: number; serverTime?: number }) {
  const [clock, setClock] = useState(() => ({ started: Date.now(), current: Date.now() }))
  useEffect(() => {
    const timer = window.setInterval(() => setClock(value => ({ ...value, current: Date.now() })), 1000)
    return () => window.clearInterval(timer)
  }, [])
  // Anchor to the backend clock so an incorrectly set browser clock does not
  // enable Resume before the backend's recorded retry time.
  const current = serverTime === undefined ? clock.current / 1000 : serverTime + (clock.current - clock.started) / 1000
  const seconds = Math.max(0, Math.ceil(until - current))
  return <div className="career-cooldown">
    <h4>{seconds > 0 ? 'Groq cooldown' : 'Recorded cooldown has ended'}</h4>
    {seconds > 0 && <p><strong role="timer" aria-label="Cooldown remaining" aria-live="off">{remainingCooldown(until, current)}</strong> remaining</p>}
    <p>You can try resuming after: <time dateTime={new Date(until * 1000).toISOString()}>{new Date(until * 1000).toLocaleString(undefined, { timeZoneName: 'short' })}</time></p>
    <p role="status">{seconds > 0 ? 'Automatic retries are off. Wait for the countdown to finish, then click Resume saved batch.' : 'Automatic retries are off. Click Resume saved batch when you are ready. Groq may apply another limit if your quota is still exhausted.'}</p>
    <p className="subtle">This is the recorded retry window, not a guarantee that all Groq quotas have reset.</p>
  </div>
}
