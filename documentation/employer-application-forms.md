# Employer application preparation

## What is implemented

InterviewBuddy now stores employer-form plans alongside application workspaces.
The first browser adapter supports Greenhouse, including employer-hosted pages
with an embedded Greenhouse application such as MongoDB. Other platforms show
an explicit unsupported status and preserve the original link and draft materials.

The app reads the actual public form schema, maps confirmed contact details,
references the original uploaded PDF/DOCX, reuses supported screening answers,
and drafts additional supported answers to actual employer questions. Generated
answers reference confirmed profile facts and pass an independent Reviewer call.
Unknown answers and unsupported claims stay blank. Personal declarations such as
work authorization, sponsorship, consent and demographic questions need the user’s
explicit answers; the agent does not infer them.

SQLite stores fields, choices, answers, source IDs, original attachment reference,
profile snapshot, source draft versions, schema fingerprint, revision, timestamps,
and preparation results. Existing profile snapshots and drafts remain immutable.
Field edits use revision checks. Refreshing preserves user answers only where the
field’s name, label, type and choices still match. Changed fields need review.

## Set up once

Browser support is optional for the rest of InterviewBuddy:

```sh
backend/.venv/bin/python -m pip install -r backend/requirements-browser.txt
backend/.venv/bin/python -m playwright install chromium
```

Restart the backend and refresh the frontend after updating. This development
session installed both Playwright and Chromium on the current Mac.

In **Find Opportunities → Settings → Application contact details**, choose
**Configure application forms**, enter confirmed contact details and save.
The auto-prepare checkbox controls preparation after discovery drafts, including
scheduled discovery. It defaults to enabled for new settings; the feature does
not create or enable discovery schedules or email delivery.

When enabled, newly drafted discovery applications prepare their form plans and
launch a headless browser pass when browser support is installed. Filling and
file upload can transmit those fields and attachments to the employer before
final submission. Turning the checkbox off prevents future automatic form work;
it does not close a browser already opened or retract transmitted information.

The machine, backend and Ollama must be available for scheduled preparation.
Local discovery still uses the selected model provider and manual cooldown policy.
If a form-answer model call fails, available answers remain saved and the form
shows the error; retries happen only when requested. A form failure does not
remove completed application drafts.

## Review an existing application

Open **Application Workspace → Application review**:

1. Choose **Prepare / refresh employer form** for an existing application, or
   **Load saved application form** for a plan prepared by discovery.
2. Inspect answers, fill missing values, and choose **Save application answers**.
3. Choose **Review application in browser**. A dedicated Chromium profile opens
   the employer application and restores the saved values and resume attachment.
4. Review the actual form, handle login/CAPTCHA/unsupported controls, and submit
   yourself. InterviewBuddy never clicks Submit, Apply or Continue.

No user credentials are copied from the everyday browser. Each workspace has an
isolated local browser profile; sessions are not mixed across applications.
Closing the app tab does not discard the SQLite plan. Closing/restarting the
browser or computer also does not discard it: use Review application to refill
again later. Keep an original uploaded resume available in the local data folder.

Changes made directly in the employer browser are **not** copied back to the local
plan. Save edits in InterviewBuddy if you want them restored later. The browser
is handed to the user after filling; no automation clicks run afterward. Submission
status is not automatically inferred from the employer page.

## Employer-side drafts versus local drafts

The browser checks only unambiguously named Save draft controls. It records an
employer draft URL only after a visible draft-saved confirmation and a supported
resume-application link. It does not assume that cookies or a URL alone preserve
form inputs. The MongoDB form inspection did not establish employer-side draft
saving, so its dependable handoff is local persistence plus browser restoration.

Where remote saving is unavailable, reminders and email link to InterviewBuddy’s
workspace. The Review application action restores the form. The original employer
URL by itself does not restore answers. No general support for Workday, LinkedIn,
Indeed or Ashby application filling is claimed by this adapter.

## Durability and isolation

Plans, settings and revisions live in `applications.sqlite3`. Dedicated browser
profiles and per-workspace process locks live under ignored
`backend/data/library/application-browsers/`. Treat that folder as private: browser
profiles can contain login cookies. It is not part of browser JSON backups.

The public form schema is fetched from a fixed Greenhouse API GET endpoint.
Browser field interaction is restricted to the exact board and job, including a
matching Greenhouse iframe on the employer host declared by that API. A schema
change is checked before filling or attachment upload. Closed jobs or unexpected
redirects stop automated filling. No submission API credentials are used.

Independent preparations reuse the same workspace plan and profile. Workers use
per-workspace process locks; a repeated Review action does not open parallel
browser sessions for the same application. Scheduled browser windows are headless
and close after preparation; review windows remain available until closed.

## Find Opportunities layout

The page has navigation to discovery, reviews, history and settings. Settings and
model-free job browsing are collapsed, reminders show three entries until expanded,
and history shows five runs at a time. Runs have compact expandable summaries,
status filtering, company/role search, and a Show older runs action. Older records
are preserved; the underlying history endpoint still returns its latest 50 batches.

## Validation

Automated tests cover durable plans, exact schema matching, revision conflicts,
retention of manual edits, unknown declarations, fact-backed answers and independent
review, restricted attachments/URLs, exact iframe identity, worker deduplication,
and save-draft button restrictions. Frontend tests cover editing before handoff,
stale-save recovery and history filtering/pagination.

A real Chromium test on a local synthetic form filled text, selected a dropdown,
attached a synthetic resume and expanded the cover-letter textbox; submission
count remained zero. Read-only live inspection of MongoDB’s public form validated
its API and embedded controls. No applicant data was filled, uploaded or submitted
to MongoDB during validation. A real candidate application has not been submitted.

References: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html),
[Playwright input actions](https://playwright.dev/python/docs/input),
[Playwright browsers](https://playwright.dev/python/docs/browsers).
