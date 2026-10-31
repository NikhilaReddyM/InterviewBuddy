# Interview Prep Companion

A local personal app for Senior/Staff software engineering interview preparation.

## Current status

Steps 1–9 are complete: React + TypeScript + Vite, validation schemas, the storage
layer and shared provider, a responsive application shell, the Weekly Planner, Resource Library, System Design Lab, calculated Dashboard, and backup/recovery controls. Dashboard opens first
by default. Navigation opens all five sections. The Dashboard, planner, library, and lab are functional. Backup export, validated import, and corrupt-data recovery are available in Settings.

## Local setup

Use Node.js 20.19+ or a newer supported LTS version, with npm.

```sh
npm install
npm run dev
```

Open the local URL printed by Vite. No API keys or external services are required.

## Checks

```sh
npm run typecheck
npm run lint
npm test
npm run build
npm run preview
```

`npm test` runs the data-model validation tests (and permits an empty suite during
scaffolding). Add feature tests as business logic is implemented. `npm run test:watch` starts interactive test mode.

## Planned implementation

Dashboard first, weekly planner, resource and revision library, System Design Lab,
light/dark themes, localStorage persistence, and validated JSON backup/restore.
Components, types, and storage logic will be organized separately.

localStorage is browser- and origin-specific, has limited capacity, and can be
cleared by browser settings. It does not sync between devices or encrypt sensitive
information. Use Settings & Backup to export JSON backups and restore validated files.

## Future ideas (not implemented)

Notion integration, a Python RAG pipeline, agents and MCP tools, evaluation suites,
fine-tuning experiments, job discovery, application drafts, and backend security
controls. This version has no authentication, cloud storage, AI integrations,
scraping, automated logins, or deployment.

## Data model

`src/types/models.ts` defines runtime Zod schemas and infers matching TypeScript
types for sessions, completion details, resources, design attempts, preferences,
the versioned dataset, and JSON backups. `src/types/defaults.ts` returns fresh
empty datasets and checklists. No browser storage is accessed by these modules.

- IDs are UUIDs; dates are valid `YYYY-MM-DD` calendar dates; timestamps are UTC ISO strings.
- Session completion is an optional object. Its presence requires actual minutes,
  takeaways (which may be empty), confidence, and a completion timestamp.
- Durations are whole minutes from 1–1440; availability permits 0–1440.
- Optional confidence is omitted until rated; supplied values must be integers 1–5.
- Optional URLs and dates are omitted when blank; forms will normalize empty inputs.
- URLs permit only HTTP/HTTPS. Notes remain plain text.
- Dataset validation rejects unexpected fields, duplicate IDs, unsupported schema
  versions, and missing linked resources. Resource deletion must detach session
  references while preserving session topic and URL snapshots.
- Availability overrides are keyed by calendar date. Defaults are 150 weekday
  minutes and zero weekend minutes, with light theme and Dashboard landing screen.
- Backup format is `{ exportedAt, data }`; the schema version lives inside `data`.

## Storage and shared state

- `src/storage/storage.ts`: validated load/save, version dispatch, backup serialization,
  5 MiB backup text limit, and explicit replacement confirmation.
- `src/app/dataActions.ts`: immutable CRUD operations, completion/undo, availability,
  preferences, UUID creation, timestamps, and resource-reference cleanup.
- `src/app/DataProvider.tsx` and `dataContext.ts`: shared state and `useAppData()`.
  Components call `dispatch(action)` or `replaceData(data, confirmed)`; both return
  a success boolean. State updates only after a successful persistent write.

Data lives under `interview-prep-companion:v1`. First visit returns defaults without
writing. Invalid JSON, unknown versions, and schema errors preserve the saved value
and block normal changes. The placeholder screen provides an error message, reload,
and raw-value recovery download. Explicitly confirmed valid replacement can recover
corrupt data; the Settings screen provides the replacement preview and confirmation.

Each save compares the current stored text with the last loaded value to reject
stale-tab writes. Reload before continuing after a conflict. This is a best-effort
check, not a transactional multi-tab database; simultaneous writes can still race.
There is no automatic cross-tab synchronization. Unknown future schema versions are rejected; version 1 data is migrated to version 2.

Tests use in-memory storage and jsdom to verify reload/remount persistence, failed
writes, corrupt-data protection, backups, CRUD, completion/undo, and references.
Real-browser refresh, download, and browser-specific quota behavior have not yet
been manually verified. Build succeeds with harmless third-party Zod comment
annotation warnings. Form normalization and backup file controls are implemented.

## Application shell

- `src/App.tsx`: navigation, Dashboard preview, Settings, and storage recovery controls.
- `src/components/`: shared Button, Field, EmptyState, native Dialog, and ConfirmDialog.
- `src/index.css`: theme tokens and shared controls; `src/App.css`: responsive shell.
- Theme is applied from saved preferences. Use the top bar toggle to switch themes.
- Settings → Start on changes the initial screen for the next refresh or visit.
- Desktop sidebar becomes a horizontally scrollable navigation row on narrow screens.
- Keyboard support includes a skip link, active-page indication, focus on navigation,
  and native modal focus containment / Escape dismissal.

All 92 automated tests pass, including shell and planner interaction tests. Native dialog
methods are stubbed in jsdom: real browser focus trapping, visual layouts, and mobile
rendering still need manual verification. No feature actions are shown until their
corresponding phases are implemented.

## Weekly Planner

`src/features/planner/WeeklyPlanner.tsx` provides Monday-start week navigation,
seven day sections, weekly totals, date-specific availability, and session actions.
`PlannerForms.tsx` supplies validated create/edit, completion, and availability forms.
`src/utils/dates.ts` uses local calendar arithmetic to avoid UTC date shifts.

- Daily defaults are 150 weekday minutes and zero weekend minutes. Overrides can
  be zero and can be removed with “Use default availability”.
- Planned minutes include all sessions, including completed sessions. Completed
  minutes use actual durations; availability warnings use planned durations.
- New sessions can use any valid date. Saving switches the planner to that week.
- Session editing preserves completion. Completion details can be edited separately.
- Undo requires confirmation and clears actual minutes, takeaways, and confidence.
- Deletion requires confirmation. Cancelling leaves saved data untouched.
- Topic, area, date, and positive whole-minute duration are validated. Completion
  requires positive actual minutes and confidence 1–5. Optional links allow HTTP/HTTPS.
- Storage errors keep forms open with entries intact; success messages appear only
  after persistence succeeds.

Automated tests cover the full create/edit/complete/edit-completion/undo/delete
workflow, remount persistence, invalid inputs, capacity warnings, default reset,
week navigation, and calendar boundaries. Visual responsive layouts and native
browser focus behavior remain manual verification items. The planner takes today's
date when opened; reopen it if leaving the app open across midnight.

## Resource Library

`src/features/resources/ResourceLibrary.tsx` provides resource management, revision
indicators, search, filters, sorting, and resource-linked session scheduling.
`ResourceForm.tsx` validates manual entries; `filterResources.ts` handles derived
search results without mutating saved records.

- Save titles, all seven areas, comma-separated tags, the specified sources, optional
  HTTP/HTTPS URLs, plain-text notes, status, optional confidence, and revision dates.
- Tags are trimmed, empty tags removed, and exact duplicates collapsed.
- Search matches title, tags, and notes case-insensitively. Area, source, status, and
  revision filters combine. Due includes today and overdue dates; future revisions
  are dates after today. Undated resources appear last when sorting by revision.
- Expand notes to read full solutions. Notes render as text, including HTML-looking
  content, and external links use safe new-tab attributes. No content is fetched.
- Schedule session prefills title, area, and URL, and records the resource ID.
  Choose date and duration in the shared planner form. Scheduling does not change
  resource status or revision date. Find the session in its week in the planner.
- Resource deletion requires confirmation and detaches session references while
  preserving copied topics, URLs, and completion data.
- Blank optional fields clear previous values on edit. Failed saves retain inputs.

Tests cover CRUD and persistence, notes rendering, tag normalization, combined
filters, revision boundaries, sorting, session prefill, cross-feature persistence,
reference cleanup, validation, and retry after storage failure. Browser visual and
native focus checks remain pending. Revision indicators use the local date when the
library opens; reopen it after midnight to refresh the due-date boundary.

## System Design Lab

`src/features/design-lab/SystemDesignLab.tsx` lists saved attempts in most recently
updated order. `DesignAttemptForm.tsx` handles editing and validation; `designFields.ts`
provides the shared section and checklist definitions.

- Required problem title; optional requirements/assumptions, scale estimates, APIs
  and data model, architecture notes, tradeoffs/failures, and missed items/next steps.
- Scalability, reliability, consistency, security, and observability checklist.
- Optional self-rated confidence from 1–5. Partial attempts can be saved with just
  a title and expanded later. Checklist completion is not a correctness score.
- Cards show last update time, confidence, and checklist progress. Expand practice
  notes to read all sections. Text renders safely without executing embedded HTML.
- Save is explicit. Cancel and Escape ask before discarding modified fields, including
  checklist/confidence changes. Keep editing preserves the draft. Native modal
  behavior blocks navigation behind the editor. A beforeunload handler requests
  the browser's warning when refreshing or closing a dirty draft; browsers control
  whether that warning is displayed. Unsaved drafts are not persisted.
- Deleting requires confirmation. Failed saves retain writing for retry and never
  replace the last successfully saved attempt.

All 92 tests, TypeScript, lint, and production build pass. Lab tests cover every
section, all checklist items, validation, CRUD, confidence clearing, remount
persistence, unsaved-change cancellation/Escape, unload-handler cleanup, failed
writes/retry, and plain-text rendering. Real-browser modal focus trapping, native
unload prompts, and responsive visual layout still need manual verification.

## Dashboard calculations

`src/features/dashboard/calculations.ts` contains pure selectors for today's sessions,
weekly totals, progress across all seven areas, and the revision queue. The planner
uses the same weekly summary to keep totals consistent. No summary counters are
persisted; every value is derived from the current saved dataset.

- Weeks run Monday–Sunday, using each session's scheduled date (not completion
  timestamp). Planned totals include both planned and completed sessions.
- Completed minutes sum actual durations, including overruns. Session completion
  percentage is completed count / scheduled count, rounded to a whole percent;
  empty groups return zero. Area progress bars use session counts, not minutes.
- Weekly availability includes daily overrides and weekday/weekend defaults.
- Today's incomplete sessions appear first. Add a session, complete/edit completion,
  or undo completion directly from the Dashboard. Changes update totals immediately
  after successful persistence. Quick actions navigate to the planner, library, or lab.
- Revision dates up to today are due, regardless of status. Upcoming covers tomorrow
  through seven days ahead, inclusive. Undated and more distant resources are omitted.
  Completing a linked session leaves the resource's revision date unchanged.
- `useToday` updates the Dashboard's local calendar date every minute and when tab
  visibility changes, so an app left open across midnight refreshes its day/week.

All 92 tests, typecheck, lint, and production build pass. New tests cover empty
summaries, area coverage, weekly boundaries, actual overruns, zero availability,
revision boundaries, record moves/deletes, completion/undo, persisted UI updates,
and midnight rollover. Real-browser visual/focus checks remain pending; the build
continues to report harmless annotation warnings from Zod.

## Backup and recovery

1. Open **Settings & Backup** and select **Export JSON backup**. Keep the downloaded
   JSON file in a safe location. It includes all records, availability overrides,
   preferences, schema version, and a UTC export timestamp.
2. To restore, select a file under **Import JSON backup** (maximum 5 MiB).
   JSON syntax, schema version, required fields, enums, IDs/references, calendar
   dates, links, durations, and confidence are checked before a preview appears.
3. Review current and incoming counts and the incoming preferences. Export current
   data first if desired. Check the replacement acknowledgment, then select
   **Replace all data**. Import replaces everything; it never merges datasets.
4. Cancel at any point before replacement to leave current data unchanged. Invalid
   files and failed writes leave existing saved data intact. The same file can be
   selected again after an error. Export does not modify saved data.

If stored data is corrupt or uses an unsupported version, use **Download original
saved value** before recovery. It preserves the exact raw value as a text file, not
an importable backup envelope. Normal JSON export is disabled while loading is
blocked so empty fallback data is not mistaken for a valid recovery backup.
Import a valid JSON backup, or choose **Start fresh instead** and explicitly confirm
to replace the unreadable value with empty defaults. Neither recovery action runs
automatically. If browser storage is unavailable, enable it and use Reload saved
data before retrying. Stale-tab conflicts require cancelling the preview and reloading.

`src/storage/files.ts` handles downloads and file reading; file size is checked
before reading, and validation runs again before persistent replacement. Async file
results are ignored after navigation. `src/features/settings/BackupControls.tsx`
provides preview, confirmation, export, and recovery actions. Native file pickers
are local; no backup content is uploaded or fetched over the network.

Verification: all 92 tests, typecheck, lint, and build pass. Backup tests cover export
contents, complete restore/remount, preview cancellation, explicit acknowledgment,
invalid/unknown-version/oversized files, quota failures and retry, corrupt-data
recovery/reset, and stale-tab conflicts. Browser download clicks/object URLs and
native dialog methods are mocked in jsdom. Actual downloaded-file handling,
responsive layouts, and native focus behavior still need real-browser verification.

## In-app back navigation

The Back button above each section heading returns to the previously visited
section, including navigation through Dashboard quick actions. Repeated selection
of the same section does not create duplicate history entries. Back is hidden
when there is no prior section. This history lasts for the current app visit and
resets on refresh; saved records and preferences are unaffected. Browser history
is not used. Returning to a section opens its initial view; temporary search filters
and selected planner weeks are not retained. Native modal editors keep the
background navigation inactive while a form is open.

## Manual job applications and reminders

Open **Job Applications** to manually record a company, role, optional HTTP/HTTPS
job link, status, submission date, next action, reminder date, and plain-text notes.
Statuses are Saved, In Progress, Applied, Interviewing, Offer, Rejected, and Withdrawn.
Applied, Interviewing, Offer, and Rejected require a submission date. The form rejects
future submission dates. Reminder dates require a next action (for example, “Finish
application” or “Follow up”). Past reminder dates are allowed and shown as overdue.

- Summary cards show submitted this Monday–today, this month through today, overall,
  unfinished (Saved/In Progress), and Interviewing. Search covers company, role,
  notes, and next action. Combine status and due-reminder filters; sort by update,
  submission date, or next reminder. Defaults and search do not alter saved records.
- Submission counts follow application dates and include rejected/withdrawn records.
  Editing a status preserves a previously recorded submission date; correct that
  date by entering a different date. Deleting an application removes it from counts.
- Dashboard shows a job-search snapshot and due/overdue reminders plus reminders in
  the next seven days. Open a reminder to edit/reschedule it; Mark reminder done
  clears its next action and reminder date while preserving status and submission.
- Reminders are in-app only. No notifications are sent while the app is closed.
  Draft generation and automatic application submission remain future work. Use
  Open application page to submit manually, then record the actual submission date.
- Unsaved job edits ask for confirmation before cancellation and request the browser
  unload warning on refresh. Failed saves keep the entries available for retry.

Implementation lives in `src/features/jobs/`. Schema version 2 adds `jobApplications`
without changing the existing localStorage key. Version 1 data and backups are
strictly validated, then migrated in memory with an empty application list. Existing
preparation records and preferences are preserved; the original stored value is
left intact until a successful write. New exports use version 2 and contain jobs;
import previews include job counts. Old backups replace all data, so importing an
old backup clears any current job applications after the usual confirmation.

Verification: 92 tests pass, with successful TypeScript, lint, and production build.
Coverage includes legacy data/backups, current backup round trips with jobs,
week/month/year submission boundaries, reminder boundaries, full job CRUD,
submission validation, search/filter/reset, persisted reloads, Dashboard rescheduling,
reminder completion, dirty cancellation, and failed-save retry. Browser visual,
focus, and downloaded-file checks remain manual; harmless Zod annotation warnings
continue during build.

## Local PDF library (Phase 2)

Resources & Revision includes a local PDF reader with page extraction, Apple Vision OCR, and saved corrections/review status. This optional feature requires the local Python backend; the original planner and notes continue working independently. See [setup and checkpoint instructions](documentation/local-pdf-library.md). PDFs, extracted content, and SQLite data remain excluded from Git and browser backups. RAG search and AI answers are not implemented yet.

## Local chunking and indexing (Phase 3)

The PDF reader now includes page-range selection, chunk previews, optional experimental unreviewed inclusion, persistent local embeddings, stale-index detection, and a passage-search diagnostic. See [Phase 3 setup and behavior](documentation/chunking-indexing-phase3.md). Answers are not generated yet.

## Retrieval comparison (Phase 4)

Search indexed PDFs with local dense, BM25 keyword, or hybrid retrieval. Compare multiple documents and run reproducible source-page evaluations; see [Phase 4 instructions](documentation/retrieval-phase4.md). Draft evaluation labels require review, and passage matches are not proof of answerability.

## Cited answers (Phase 5)

The PDF library includes **Ask my PDFs**, using LangChain, hybrid retrieval over the three Dynamic Programming PDFs, and configurable Groq generation. Answers include source-page citations, exact evidence quotes, and unreviewed-source labels. See [Groq setup and usage](documentation/cited-qa-phase5.md) and the [Week 2 submission draft](documentation/week2-submission-draft.md). Generation tests are mocked; configure your own local API key/model to try real answers. Tracing and systematic answer evaluation are deferred.

## Career Profile: PDF and DOCX resume ingestion

Start the local backend with `backend/.venv/bin/python backend/documents.py serve`
and the frontend with `npm run dev`. Open **Career Profile**, choose a text-based
`.docx` or text-based `.pdf` resume (maximum 5 MiB), and select **Upload and extract**. Inspect the
extracted text and use **Download original resume** to retrieve the saved file.
Paragraphs and table text are extracted in document order; formatting, images,
headers, and footers are not reproduced. Image-only or invalid files are rejected.
Identical uploads reuse the existing record. Saved resumes reload when reopening
the screen. Local storage is under `backend/data/library/resumes/` (or the
`INTERVIEWBUDDY_DATA` directory's `resumes/` child), excluded from Git and browser
JSON backups. This feature makes no model calls. Structured profile extraction,
confirmation, and agents are subsequent milestones.

Resume API: `GET /api/resumes`, raw DOCX `POST /api/resumes?filename=resume.docx`
(with `X-InterviewBuddy: local`), and `GET /api/resumes/{id}/original`.

PDF resume extraction uses local macOS Swift/PDFKit, supports up to 30 pages, and rejects pages without readable text. Scanned PDFs require OCR and are not supported by this resume upload yet. Restart the backend after updating to register PDF support.

### Generate and confirm a career profile

In Career Profile, select a saved resume and click **Generate profile**. This
explicit action sends its extracted text to the configured Groq model using the
existing `GROQ_API_KEY` and `GROQ_MODEL` backend configuration. Uploading alone
still makes no model calls. Generation has a 60-second provider timeout, one bounded evidence-repair attempt, a 60,000-character input limit, and disabled cloud tracing.

Review facts grouped into experience, skills, education, projects, and
achievements. Edit or remove facts, or add facts with exact supporting resume
quotes. Exact quote validation establishes text provenance, not semantic support;
review both the statement and quote. Enter target roles, locations, work
arrangement, and exclusions separately; preferences are never inferred from the
resume. **Save draft** persists work; **Confirm profile** saves an explicitly
reviewed version. Subsequent draft saves clear confirmation. Revision checks
reject stale writes and preserve edits for recovery. Existing profiles cannot be
automatically regenerated over user corrections. Different resumes have separate
profiles. Profiles remain in the local resume SQLite database, outside browser
backups. No agents, job discovery, or Mem0 writes run at this milestone.

Profile evidence validation tolerates whitespace-only differences and stores the exact original resume span. Changed words, punctuation, or metrics remain rejected. An invalid generated quote triggers one corrective model call; a second failure leaves existing data untouched.

Profile generation now asks Groq for numbered source passage references instead
of copied quotes. The backend validates IDs and derives verbatim evidence spans
from the original extracted text. Multiple nearby references include intervening
text; evidence exceeding 4,000 characters is rejected. This prevents quote-copying
errors but does not establish semantic support; human confirmation remains required.

## Persistent application workspaces

**Application Workspaces** stores jobs, draft versions, review findings, and review
reminders in local SQLite, each linked to a preserved confirmed profile version.
LangGraph SQLite checkpoints support paused setup runs across backend restarts.
See [workspace usage, API, storage, and limitations](documentation/application-workspaces.md).
This milestone adds storage and resumable setup; automated drafting is next.

## Application agents for a pasted job

In an Application Workspace, use **Prepare application** to run the Analyst,
Coordinator, Writer, and Reviewer against the saved job and confirmed profile.
The workflow may pause for clarification, revise drafts, recommend skipping a role,
or finish with materials ready for your review. See [agent flow usage and recovery](documentation/application-agent-flow.md).
This explicit action uses your configured Groq provider; job search and submission
are not part of this milestone.

## Find opportunities and prepare review drafts

**Find Opportunities** searches supported public job feeds, matches jobs against a
confirmed profile, prepares drafts without intermediate questions, and saves
review reminders. Read [coverage, operation, recovery, and scheduling preparation](documentation/opportunity-discovery.md).
Runs are triggered manually today; no recurring schedule is installed. The worker
can run independently of the UI for future scheduling.

## Application review queue

Open **Review applications** from the Dashboard, or select a reminder in **Find
Opportunities**, to review match reasoning, gaps, unanswered questions, and draft
materials. Edit drafts as new versions and follow the original application link.
Automatic reminders use configurable delay/timezone preferences and do not
reappear merely because a run is retried. See [review queue usage and behavior](documentation/application-review-queue.md).

## Broader job sources without model quota

**Find Opportunities → Browse jobs — no AI** searches public listings from selected
Greenhouse/Ashby employers alongside Remotive and Arbeitnow. Filter by location and
work arrangement, inspect the source, and save jobs for later without Groq calls.
See [coverage, configuration, and limitations](documentation/broader-job-coverage.md).

## Scheduled discovery

In **Find Opportunities → Scheduled discovery**, configure weekdays, time,
timezone, profile, and batch size. Schedules start paused until you explicitly
enable one. The local backend must remain running; Groq cooldown retries stay
manual. See [scheduled discovery setup and behavior](documentation/scheduled-discovery.md).
