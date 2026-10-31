# Email review digest

## Configure delivery

The feature is disabled by default. No email account is connected, no message is
sent, and no recipient is inferred from your resume during installation.

Set your provider's SMTP connection settings in ignored `backend/.env` (examples
are listed in `backend/.env.example`):

```dotenv
SMTP_HOST=your.smtp.server
SMTP_PORT=465
SMTP_SECURITY=ssl
SMTP_FROM=you@example.com
SMTP_USERNAME=your-login
SMTP_PASSWORD=your-provider-credential
```

Use `ssl` for implicit TLS or `starttls` for a TLS upgrade (commonly port 587).
Both verify the server certificate. Username/password must be configured together;
a TLS relay that does not require authentication can leave both empty. Credentials
stay in the backend and are never returned to the browser. Restart after changes.

In **Find Opportunities → Email review digest → Configure email digest**:

1. Enter the recipient, delivery days/time/timezone, and app URL.
2. Choose the due-date window: 0 includes overdue/today, 1 adds tomorrow, up to 7.
3. Explicitly check **Enable email delivery and scheduled digests to this recipient**
   and save when you want delivery enabled. SMTP configuration is required first.
4. Create a preview, inspect it, and use **Send this digest now** for an explicit
   manual send. A preview alone never sends email.

Saving enabled settings calculates the next future scheduled delivery. The backend
and computer must stay running/awake. An email timer checks local due times every
30 seconds; it sends only at the configured times. If the backend was off for
several days, missed times coalesce into one current digest rather than a burst.
Uncheck enabled and save to stop future emails. A send already in progress may
finish; disabling cannot retract a message the mail server already accepted.

## Content and links

Digests include pending review reminders with saved drafts whose due dates fall
within the chosen window. Multiple reminders for the same workspace produce one
entry. Completed reminders and applications without saved drafts are excluded.
Up to 25 applications are listed; additional pending reviews are noted.

Each item contains the company, role, due date, readiness/incomplete label, match
reason, limited cautions/unanswered questions, an InterviewBuddy review link, and
the original application link. Full resumes, full draft text, and credentials are
not included. Email summaries are informational; application materials still need
your final review. No applications are submitted by this feature.

`app_base_url` defaults to `http://localhost:5173`. Links use
`?workspace_id=UUID` and open that workspace's review package. Localhost links only
work on the machine running the app, with its frontend/backend available. Set a
reachable app origin only if you have separately configured hosting/access. This
feature does not expose the local app publicly or deploy it.

Generating previews or sending digests makes no Groq calls. Discovery schedules
and manual Groq cooldown recovery are independent and remain unchanged.

## Duplicate protection and failures

A persisted preview fixes the recipient, sender, subject, content, and settings
revision. Settings changes require a new preview before a manual send. Concurrent
email operations are serialized by a file lock. Preview IDs are content hashes;
delivery records also have a unique hash of recipient/sender/subject/body. Repeated
clicks or a scheduled send with the exact same content/date do not resend it.
The date is part of the digest subject, so a future day's digest can remind you
again about reviews still pending. Changed queue content can produce a different
preview; a deliberate manual send of that updated digest is a new delivery.

The app distinguishes:

- **sent**: the SMTP server accepted the message; inbox delivery is not guaranteed.
- **failed**: failure/rejection was known before acceptance. Fix configuration and
  use **Retry failed email** explicitly. There is no automatic retry.
- **unknown**: the connection or process ended after delivery may have begun. Check
  the recipient inbox and SMTP logs. The app blocks retries to avoid duplicates.
- **sending**: an email operation is in progress. After an interrupted process, it
  becomes unknown when the unlocked sender state is inspected or the timer runs.
- **skipped_empty**: no pending reviews with saved drafts were due, so no email.

Each scheduled slot is claimed once and advances to its next future time before
sending. A crash cannot cause an automatic resend of that slot. No transport can
guarantee exactly-once inbox delivery after an ambiguous network failure; unknown
outcomes are preserved instead of retried. There is currently no automatic resend
or UI override for unknown outcomes.

## Storage and API

Email settings, immutable previews, delivery metadata, and scheduled-slot history
are stored in `applications.sqlite3`, separate from browser backups. They contain
recipient addresses and review summaries, so keep backend backups private. SMTP
credentials remain in environment configuration, outside that database.

- `GET /api/email-digest`: settings, SMTP readiness (no secrets), delivery history.
- `PUT /api/email-digest`: save settings with the current `revision`.
- `POST /api/email-digest/preview`: create a preview without sending.
- `POST /api/email-digest/send`: explicitly send `{preview_id}`.
- `POST /api/email-digest/retry`: explicitly retry a known failed `{preview_id}`.

The usual local-request header is required for mutations. Readiness checks do not
connect to SMTP or verify passwords. Configure a real account and send a preview
to validate actual delivery; development tests use mock SMTP and send no real mail.

## Verification

Tests cover disabled defaults, preview-only behavior, SMTP SSL/STARTTLS and login,
manual and scheduled duplicate protection, excluding completed reminders, skipping
empty digests, stale-recipient protection, known failures and explicit retry,
ambiguous delivery and process interruption without resend, API settings, frontend
preview/send controls, and workspace deep links. No real email was sent during
implementation and no delivery account was configured automatically.

A failed email can be retried explicitly from delivery history after changing the schedule time or days. Changing the recipient, sender, or application URL requires a fresh preview. History shows the last attempt time and attempt count. A scheduled slot that encounters the same failed digest does not resend it; use **Retry failed email**.
