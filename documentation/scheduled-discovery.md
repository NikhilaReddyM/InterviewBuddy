# Scheduled discovery

## Configure

Restart the backend and refresh the app. Open **Find Opportunities → Scheduled
discovery → Configure schedules**.

Choose a name, resume profile, run time, timezone, weekdays, and batch size (1–3).
Schedules are saved **paused by default**. Check **Enable scheduled discovery
using my confirmed profile** when you want it active. The selected resume must
have a confirmed Career Profile to enable the schedule. No schedules are created
or enabled by an update or backend startup.

The schedule list shows its next run in its configured timezone and recent run
history. Use **Pause schedule** to disable future runs and **Enable schedule** to
calculate a new next run. Edit can change timing, days, resume, or batch size.
A pause does not cancel an already-started batch. A stale settings save is rejected;
reload and edit the current schedule instead of overwriting another tab's changes.

Each execution starts fresh discovery with the latest confirmed profile for the
selected resume and the saved review reminder preferences. It uses the configured
public sources and existing matching/drafting/review flow. AI discovery needs
available Groq quota. Model-free browsing remains separate and manually triggered.
Email digests are a separate opt-in feature; see [email setup](email-digest.md). No automatic application submission is enabled.

## Local execution and missed runs

The scheduler runs within the Python backend. The computer must be awake and the
backend running; closing the React tab does not stop it. Turning off the backend
or putting the computer to sleep prevents execution. There is no cloud hosting,
OS startup service, or external cron job installed by this feature.

A daemon checks SQLite for due schedule timestamps every 30 seconds. These local
checks make **no model or job-source requests**. External calls happen only for
a due enabled schedule. The time is approximate to this interval and worker
availability, not a real-time guarantee.

If the backend was off through several scheduled times, the next startup coalesces
missed times into at most one overdue execution per schedule, then advances to the
next future calendar time. It does not launch a burst for every missed day. History
shows the claimed scheduled time separately from the actual start time.

Daylight-saving handling uses the schedule's IANA timezone. An ambiguous fall-back
time runs only at its first occurrence. A nonexistent spring-forward time shifts
to the first valid minute that morning. For example, 02:30 becomes 03:00 on a day
where clocks jump from 01:59 to 03:00.

## Retries and overlap

Groq cooldowns remain **manual**. A scheduled run that gets throttled pauses its
saved discovery batch; use **Resume saved batch** after the cooldown when ready.
The scheduler never resumes waiting, failed, or interrupted batches. Subsequent
regular schedule times may start new discovery; these are separate calendar slots,
not retries of an earlier batch. Duplicate workspace/draft/reminder protection
continues to apply.

If the provider is already in a recorded cooldown at a scheduled time, that slot
is marked **skipped**, with no model calls. If another discovery worker is active,
the slot is also skipped. If the worker becomes busy between claiming a slot and
execution, its saved batch is marked deferred for manual recovery.

Each calendar slot has a unique `(schedule_id, scheduled_for)` record and a stable
batch request key. Process locks serialize schedulers across backend processes;
the existing discovery worker lock serializes actual discovery. Repeated checks
and restarts cannot create duplicate batches for the same claimed slot.

If a process stops after claiming a slot, the next scheduler check marks it
**interrupted**, reconnecting the saved batch if needed. It does not automatically
replay model work. Open the linked discovery history and resume manually.

## Storage and API

Schedules and slot history are stored in `applications.sqlite3`, under the same
local backend data directory as other workspaces. They are outside browser JSON
backups. Enabled status, timezone, next run, and slot history survive restarts.

- `GET /api/discovery-schedules`: settings, next times, last ten runs per schedule.
- `POST /api/discovery-schedules`: create with a stable `request_id`.
- `PUT /api/discovery-schedules/{id}`: edit or pause/enable with `revision`.

Mutations require the existing `X-InterviewBuddy: local` header. No schedule is
enabled implicitly; the UI requires an explicit checkbox or Enable action.

A process manager can alternatively perform a single due-schedule check:

```sh
backend/.venv/bin/python backend/run_scheduled_discovery.py
```

This executes due enabled schedules and may use configured provider credits.
It does not install a cron job or retry old batches. Use the same data directory
as the backend; `--data-dir` or `INTERVIEWBUDDY_DATA` selects a different one.

## Validation

Tests cover timezone next-run calculations, weekdays, spring gaps and fall-back,
paused creation, enable/pause changes, stale revisions, latest profile snapshots,
coalescing missed days, duplicate slot prevention across reopened stores, provider
cooldown and worker-busy skips, interrupted history recovery, no automatic cooldown
resumption, API settings, and the UI's explicit enable controls. Tests use synthetic
profiles and mocked processors; no real user schedule or model call is activated.
