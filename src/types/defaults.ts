import { SCHEMA_VERSION } from './models'
import type { AppData, DesignChecklist } from './models'

// Factories return fresh objects so callers cannot mutate shared defaults.
export function createEmptyData(): AppData {
  return {
    schemaVersion: SCHEMA_VERSION,
    sessions: [],
    resources: [],
    designAttempts: [],
    jobApplications: [],
    availabilityOverrides: {},
    preferences: {
      theme: 'light',
      defaultLandingScreen: 'dashboard',
      defaultWeekdayMinutes: 150,
      defaultWeekendMinutes: 0,
    },
  }
}

export function createEmptyChecklist(): DesignChecklist {
  return {
    scalability: false,
    reliability: false,
    consistency: false,
    security: false,
    observability: false,
  }
}
