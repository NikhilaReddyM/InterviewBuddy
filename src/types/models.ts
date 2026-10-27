import { z } from 'zod'

export const SCHEMA_VERSION = 2 as const

export const PREPARATION_AREAS = [
  'Coding',
  'System Design',
  'Behavioral',
  'Architecture / Project Stories',
  'Low-Level Design',
  'Backend Practice',
  'AI and personal projects',
] as const

export const RESOURCE_SOURCES = [
  'Interview Kickstart', 'LeetCode', 'Hello Interview', 'ByteByteGo',
  '1point3acres', 'Notion', 'Other',
] as const
export const RESOURCE_STATUSES = ['Not Started', 'In Progress', 'Reviewed'] as const
export const SCREENS = ['dashboard', 'planner', 'resources', 'design-lab', 'jobs', 'settings'] as const
export const THEMES = ['light', 'dark'] as const

export const preparationAreaSchema = z.enum(PREPARATION_AREAS)
export const resourceSourceSchema = z.enum(RESOURCE_SOURCES)
export const resourceStatusSchema = z.enum(RESOURCE_STATUSES)
export const idSchema = z.uuid()
// Calendar dates intentionally have no time or timezone. Zod checks leap years too.
export const calendarDateSchema = z.iso.date()
export const timestampSchema = z.iso.datetime()
export const confidenceSchema = z.number().int().min(1).max(5)
export const durationSchema = z.number().int().positive().max(1440)
export const availabilitySchema = z.number().int().min(0).max(1440)
export const resourceUrlSchema = z.url({ protocol: /^https?$/ })
const titleSchema = z.string().trim().min(1)
const recordMetadata = {
  id: idSchema,
  createdAt: timestampSchema,
  updatedAt: timestampSchema,
}

export const sessionCompletionSchema = z.strictObject({
  actualMinutes: durationSchema,
  takeaways: z.string(),
  confidence: confidenceSchema,
  completedAt: timestampSchema,
})

export const studySessionSchema = z.strictObject({
  ...recordMetadata,
  topic: titleSchema,
  area: preparationAreaSchema,
  date: calendarDateSchema,
  plannedMinutes: durationSchema,
  resourceUrl: resourceUrlSchema.optional(),
  resourceId: idSchema.optional(),
  // Presence means completed. Absence means planned; no duplicate status flag.
  completion: sessionCompletionSchema.optional(),
})

export const resourceSchema = z.strictObject({
  ...recordMetadata,
  title: titleSchema,
  area: preparationAreaSchema,
  tags: z.array(titleSchema),
  source: resourceSourceSchema,
  url: resourceUrlSchema.optional(),
  notes: z.string(),
  status: resourceStatusSchema,
  confidence: confidenceSchema.optional(),
  nextRevisionDate: calendarDateSchema.optional(),
})

export const designChecklistSchema = z.strictObject({
  scalability: z.boolean(),
  reliability: z.boolean(),
  consistency: z.boolean(),
  security: z.boolean(),
  observability: z.boolean(),
})

export const designAttemptSchema = z.strictObject({
  ...recordMetadata,
  title: titleSchema,
  requirementsAndAssumptions: z.string(),
  scaleEstimates: z.string(),
  apisAndDataModel: z.string(),
  architectureNotes: z.string(),
  tradeoffsAndFailureScenarios: z.string(),
  missedAndNextSteps: z.string(),
  checklist: designChecklistSchema,
  confidence: confidenceSchema.optional(),
})

export const JOB_STATUSES = ['Saved', 'In Progress', 'Applied', 'Interviewing', 'Offer', 'Rejected', 'Withdrawn'] as const
export const jobApplicationInputSchema = z.strictObject({
  company: titleSchema,
  role: titleSchema,
  url: resourceUrlSchema.optional(),
  status: z.enum(JOB_STATUSES),
  applicationDate: calendarDateSchema.optional(),
  nextAction: titleSchema.optional(),
  reminderDate: calendarDateSchema.optional(),
  notes: z.string(),
}).superRefine((job, ctx) => {
  if (['Applied', 'Interviewing', 'Offer', 'Rejected'].includes(job.status) && !job.applicationDate) {
    ctx.addIssue({ code: 'custom', path: ['applicationDate'], message: 'Enter the date this application was submitted.' })
  }
  if (job.reminderDate && !job.nextAction) {
    ctx.addIssue({ code: 'custom', path: ['nextAction'], message: 'Describe what this reminder is for.' })
  }
})
export const jobApplicationSchema = jobApplicationInputSchema.safeExtend(recordMetadata)
export type JobApplication = z.infer<typeof jobApplicationSchema>

export const preferencesSchema = z.strictObject({
  theme: z.enum(THEMES),
  defaultLandingScreen: z.enum(SCREENS),
  defaultWeekdayMinutes: availabilitySchema,
  defaultWeekendMinutes: availabilitySchema,
})

export const appDataSchema = z.strictObject({
  schemaVersion: z.literal(SCHEMA_VERSION),
  sessions: z.array(studySessionSchema),
  resources: z.array(resourceSchema),
  designAttempts: z.array(designAttemptSchema),
  jobApplications: z.array(jobApplicationSchema),
  availabilityOverrides: z.record(calendarDateSchema, availabilitySchema),
  preferences: preferencesSchema,
}).superRefine((data, ctx) => {
  // IDs are unique across the whole dataset, not just within each collection.
  const ids = new Set<string>()
  for (const collection of ['sessions', 'resources', 'designAttempts', 'jobApplications'] as const) {
    data[collection].forEach((record, index) => {
      if (ids.has(record.id)) {
        ctx.addIssue({ code: 'custom', path: [collection, index, 'id'], message: 'Duplicate record ID' })
      }
      ids.add(record.id)
    })
  }
  const resourceIds = new Set(data.resources.map((resource) => resource.id))
  data.sessions.forEach((session, index) => {
    if (session.resourceId && !resourceIds.has(session.resourceId)) {
      ctx.addIssue({
        code: 'custom', path: ['sessions', index, 'resourceId'],
        message: 'Linked resource does not exist',
      })
    }
  })
})

export const backupSchema = z.strictObject({
  exportedAt: timestampSchema,
  data: appDataSchema,
})

// Infer types from validation schemas so runtime and compile-time rules agree.
export type PreparationArea = z.infer<typeof preparationAreaSchema>
export type ResourceSource = z.infer<typeof resourceSourceSchema>
export type ResourceStatus = z.infer<typeof resourceStatusSchema>
export type Screen = typeof SCREENS[number]
export type Theme = typeof THEMES[number]
export type SessionCompletion = z.infer<typeof sessionCompletionSchema>
export type StudySession = z.infer<typeof studySessionSchema>
export type Resource = z.infer<typeof resourceSchema>
export type DesignChecklist = z.infer<typeof designChecklistSchema>
export type DesignAttempt = z.infer<typeof designAttemptSchema>
export type Preferences = z.infer<typeof preferencesSchema>
export type AppData = z.infer<typeof appDataSchema>
export type Backup = z.infer<typeof backupSchema>
