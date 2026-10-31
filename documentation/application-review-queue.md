# Application review queue

Restart the backend and refresh the frontend after updating.

## Review applications

Use **Dashboard → Review applications** or **Find Opportunities → Your review
reminders**. Each reminder opens its application workspace. The review package
opens automatically when arriving from the queue. Otherwise click **Open review
package** in an existing workspace.

The package shows the profile version, original application link, match reasoning
and cautions, analysis gaps, questions flagged by agents, latest drafts, reviewer
findings, and pending/completed reminders. Reading it makes no model calls. Older
discovery match reasons are recovered from saved batch history when needed.
A running workflow can temporarily make analysis unavailable; refresh the package
after the agents finish. Deferred applications with no drafts are explicitly marked
as not ready to submit.

## Edit and save

Use **Edit cover letter**, **Edit resume suggestions**, or **Edit screening answers**.
Saving appends a new draft version retaining the profile snapshot and a link to the
base draft. It never overwrites earlier content. Conflicting saves against an old
head version return HTTP 409 and retain the text in the editor. Repeating the same
save request returns the same version. Navigation and browser-close warnings protect
unsaved changes where supported by the browser.

Human edits are labeled **not automatically re-reviewed**. Findings from earlier
drafts remain in history and are labeled separately. Agent-flagged questions do not
automatically clear when free-text draft answers are edited; review them manually.
Use **Mark review done** to complete the reminder. This does not mark the job as
applied, approve every claim, or submit an application.

## Automatic review reminders

Under **Find Opportunities → Review reminder preferences → Configure reminders**:

- Enable or disable automatic creation.
- Choose a delay of 0–30 days after draft preparation.
- Set an IANA timezone, such as `America/New_York`.

Configured timing is the default for new discovery and reassessment batches.
Uncheck **Use configured reminder timing instead of a specific date** to provide an
explicit review date. Discovery resolves the configured date when the batch is
created; saved batch retries retain that date. Direct workspace agent completion
and manual draft creation use the same preferences. Existing reminder dates remain
unchanged when preferences change.

Only saved drafts get automatic review reminders; rejected roles do not. Partial
packages are marked incomplete. One automatic reminder per workspace is reused
across retries. An unchanged draft/status fingerprint does not reopen a reminder
already marked done. Newly generated draft versions or a changed completion state
can reactivate that same reminder instead of creating another. Older discovery
reminder keys are reused for compatibility. Manual reminders remain independent.

Preferences, match context, edit lineage, and reminder fingerprints are local SQLite
tables in `applications.sqlite3`, separate from browser backups. Profile snapshots,
job descriptions, existing drafts, and manual tracker records are preserved.
Groq retries remain manual. Recurring discovery and [email digests](email-digest.md) are separate opt-in settings; neither is enabled by default.

## API

- `GET/PUT /api/review-preferences`
- `GET /api/workspaces/{id}/review`
- `POST /api/workspaces/{id}/drafts/{draft_id}/edit` with `{content, request_id}`
- Existing reminder completion endpoint and discovery review-queue endpoint remain.

Mutation requests require the normal `X-InterviewBuddy: local` header.
