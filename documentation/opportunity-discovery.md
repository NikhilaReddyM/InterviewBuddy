# Autonomous opportunity discovery

## What to do

1. In Career Profile, confirm your resume facts and set target roles, locations,
   work arrangement, and exclusions. Missing preferences remain unknown.
2. Open **Find Opportunities**. Choose the resume, a batch size of 1–3, and a
   review date. Click **Find opportunities** once.
3. Leave the agents to search, match, draft, review, and save reminders. There are
   no intermediate clarification questions in discovery runs.
4. Come back to **Your review reminders**, open a workspace, inspect drafts and
   warnings, edit as needed, and submit through the linked application page yourself.

Restart the backend after updating. The backend needs to stay running while a
batch executes. Leaving the frontend does not stop it. Closing the backend stops
execution; use **Resume saved batch** to recover. This milestone does not install
or activate a recurring schedule, send email, or submit applications.

## Sources and scope

The current integrations read public job feeds, not arbitrary employer sites:

- [Remotive API](https://github.com/remotive-com/remote-jobs-api): remote roles,
  including candidate location restrictions. Public data is delayed by 24 hours.
  Remotive attribution and links are preserved. Successful feed reads are cached
  for six hours in SQLite, respecting the provider's advice of at most four
  requests per day.
- [Arbeitnow API](https://www.arbeitnow.com/blog/job-board-api): mainly European
  listings, including remote and nonremote jobs. The first feed page is read;
  this implementation does not enumerate every page or cover every country.

Only fixed HTTPS feed URLs are fetched. Requests have timeouts and response-size
limits; HTML becomes plain text and is never executed. No resume or profile data
is sent to job boards. Profile facts, preferences, listings, and generated drafts
are sent to the configured Groq model for planning, matching, writing, and review.
Cloud tracing is disabled. No company career-page fetch or current vacancy
verification is performed beyond the public feed snapshot. Check availability
and hiring eligibility when reviewing the application link.

## Agent behavior

A Search Planner chooses up to six role/skill keywords from the confirmed profile
and preferences. Local keyword and work-arrangement filtering shortlists at most
12 unique jobs from the source pool. The Matcher evaluates profile fit, exclusions,
location restrictions, and uncertainty, linking matches to confirmed fact IDs.
Eligible matches scoring at least 65/100 are considered in score order. Scores
are model judgments, not probabilities or proof of eligibility. Skipped match
reasons are available in discovery history.

Up to the chosen number of new roles are attempted per batch. Duplicates do not
consume that budget. Company, role, and location form a conservative cross-source
identity, so similar postings in the same location may be merged. Repeat batches
for the same resume do not generate another workspace for that identity. Manual
workspaces are not deduplicated against discovery records.

Each selected role uses the existing Analyst/Coordinator/Writer/Reviewer graph in
`autonomous` mode. Clarification is removed from allowed actions. If the model
still asks for it, the backend continues drafting/review instead. Unknown facts
remain unanswered and are surfaced in analysis, screening answers, or reviewer
findings. Explicit incompatibilities can cause rejection. Three Writer passes
remain the upper bound. Automated review does not guarantee factual correctness.
Human review remains required before submission.

Drafts, reviews, and final reminders are saved in SQLite. An incomplete run with
saved drafts gets a reminder clearly labeled incomplete. If there are no drafts,
its failure remains visible in discovery history. A rejected role gets no draft
review reminder. Review reminders appear in **Find Opportunities** and their
workspace, independently of the older browser-based manual tracker.

## Durability and later scheduling

`discovery_batches` in `applications.sqlite3` stores the input, immutable profile
snapshot reference, search plan, shortlist, match decisions, per-job status,
workspace/run IDs, activity, and failures. Each transition is persisted. All jobs
in a batch use the profile version confirmed at batch creation, even if that
profile is edited or unconfirmed while the batch runs.

A process lock serializes discovery workers across processes. The FastAPI endpoint
returns a saved batch and starts its worker in a background task. The UI polls
saved state; it does not drive execution. A second worker leaves its batch queued
if the first holds the lock. Resume a queued batch when the first finishes.

Stable request IDs protect batch creation, workspace creation, draft versions,
and reminders. A persisted workspace-write intent allows recovery if a process
stops after inserting the workspace but before recording its ID. Existing failed
application steps receive one bounded retry per batch attempt; deferred work can
resume later from LangGraph checkpoints. Source failures are cached for ten
minutes to prevent repeated calls to unavailable providers. A working source can
continue when the other fails. Completed batches are not rerun.

The worker is separate from HTTP and accepts an existing batch ID:

```sh
backend/.venv/bin/python backend/run_discovery.py --batch-id BATCH_ID
```

A future scheduler can create and execute a new batch with an idempotency key for
its scheduled slot:

```sh
backend/.venv/bin/python backend/run_discovery.py \
  --resume-id RESUME_ID --review-date YYYY-MM-DD --limit 3 \
  --request-id UNIQUE_SCHEDULE_SLOT
```

No schedule is active. A future scheduler must provide dates in the user's chosen
timezone, keep the backend worker environment available, and resume interrupted
batches. These commands use the configured model and sources, so they have the
same inference costs and data transfers as clicking Find Opportunities.

## Validation

Mocked tests exercise full discovery through real LangGraph checkpoints and
SQLite: matching, draft generation, no clarification pauses, review reminders,
source failures, restart recovery, duplicate protection, profile-version stability,
write-interruption recovery, batch limits, HTML/URL validation, and HTTP routes.
Frontend tests cover starting a batch, review-queue navigation, and service errors.
A live integration check fetched both public feeds without sending candidate data.
No end-to-end discovery run using a real user profile was performed in this change.

Matching evaluates at most three jobs per model request, with a 12,000-character
job-data budget per group. Only candidate fact statements and categories are sent
to the Matcher; original evidence remains in the immutable profile snapshot and is
available during drafting/review. Matching decisions are checkpointed per group,
so resuming a failed batch does not reevaluate finished groups or refetch listings.
Provider request-size failures are distinguished from invalid structured output.
