import { useEffect, useState } from 'react'
import { calendarDate } from './dates'

export function useToday() {
  const [today, setToday] = useState(() => calendarDate(new Date()))
  useEffect(() => {
    const refresh = () => setToday(calendarDate(new Date()))
    const timer = window.setInterval(refresh, 60_000)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [])
  return today
}
