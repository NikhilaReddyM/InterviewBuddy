# Persistent application workspaces

## Use

Install backend dependencies with `backend/.venv/bin/pip install -r backend/requirements.txt`
(or use `backend/requirements.lock.txt` for the tested dependency set), restart
`backend/.venv/bin/python backend/documents.py serve`, and refresh the frontend.

1. Confirm a resume profile in **Career Profile**.
2. Open **Application Workspaces** and create a job workspace using that resume.
3. Save draft versions, add findings for a specific draft, and schedule review reminders.
4. Reopen any workspace after refresh or backend restart to retrieve those records.
5. Under **Workflow setup & saved runs**, prepare a run. It persists and pauses
   for application instructions. Reopen it later and save instructions to resume.

This milestone is persistence infrastructure. Drafts are entered manually; future
agents will use the same backend records. The setup graph finishes at
`ready_for_agents`, which does not indicate an application has been generated,
reviewed, approved, or submitted. It performs no model calls or external actions.

The existing manual job tracker remains browser-based. Workspaces have an optional
`tracker_id` for later linking but do not migrate, synchronize, or modify existing
tracker records. Workspace reminders appear inside their workspace; they do not
send email or run a background scheduler.

## Storage and profile provenance

All new files live under `backend/data/library/` (or `INTERVIEWBUDDY_DATA`):

- `resumes/resumes.sqlite3`: existing editable career profiles and resume text.
- `applications.sqlite3`: job workspaces, immutable confirmed profile snapshots,
  immutable draft versions, draft-specific review findings, reminders, and run IDs.
- `application-checkpoints.sqlite3`: LangGraph SQLite checkpoints and pending writes.
- `run-locks/`: per-run process locks released automatically if a process exits.

On workspace creation the backend reads the confirmed profile, copying its payload,
revision, resume ID, and confirmation timestamp into an immutable snapshot. A
workspace and every draft in it reference that snapshot by foreign key. Updating
or unconfirming the Career Profile does not change previous workspace evidence.
Create a new workspace to use a newer confirmed profile. A failed or unconfirmed
profile cannot start a new workspace.

Draft edits are saved as new versions rather than overwriting old drafts. Findings
reference a specific draft and cannot be attached across workspaces. All record
creation APIs accept stable request IDs; identical retries return the same record,
while conflicting payloads return HTTP 409. Foreign keys are enabled on every
application database connection. Database transactions protect application writes.

LangGraph uses a stable database run ID as its `thread_id`, `SqliteSaver` on disk,
and `interrupt`/`Command(resume=...)`. The graph is reconstructed on every request,
so its state is not dependent on a live Python object. Resume requires the current
checkpoint ID, rejects stale input, and recognizes identical completed retries.
Concurrent execution of the same run is rejected with HTTP 409 using a process
lock. Read the latest run state to recover. Repeating a run creation request can
also recover a process interruption before the initial human pause.

Cloud tracing is disabled for graph operations. These files remain excluded from
Git and browser JSON backups. With the backend stopped, copy the complete data
directory for a consistent local backup. The app does not yet provide a backend
backup/export UI. Local loopback access controls apply to every new endpoint.

## API

All write requests need `X-InterviewBuddy: local` and JSON content type.

| Method | Endpoint | Purpose |
|---|---|---|
| GET / POST | `/api/workspaces` | List or create a workspace |
| GET | `/api/workspaces/{id}` | Job, profile snapshot, drafts, findings, reminders, run IDs |
| POST | `/api/workspaces/{id}/drafts` | Append a draft version |
| POST | `/api/workspaces/{id}/findings` | Append a finding for a workspace draft |
| POST | `/api/workspaces/{id}/reminders` | Save a review reminder |
| POST | `/api/workspaces/{id}/reminders/{reminder_id}/complete` | Mark reminder done |
| POST | `/api/workspaces/{id}/runs` | Start/recover a run using `request_id` |
| GET | `/api/workspaces/{id}/runs/{run_id}` | Inspect state and checkpoint |
| POST | `/api/workspaces/{id}/runs/{run_id}/resume` | Resume with `checkpoint_id` and `instructions` |

## Verification

Backend tests cover record reloads, immutable profile/draft history, idempotency,
cross-workspace checks, confirmation gating, stale resume rejection, run locking,
HTTP routes, reminder completion, and checkpoint resumption in a separate Python
process. Frontend tests cover reopening a saved workspace, saving a draft, and
retaining text on save failure. No real resume or model provider is needed.

LangGraph references:
[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and
[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
