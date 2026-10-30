# Pasted-job application agent flow

## Use

Restart the Python backend after updating and refresh the frontend. Confirm a
Career Profile, create or open an **Application Workspace**, and paste a real job
description when creating it. In **Application Copilot**, optionally enter writing
instructions and additional screening questions (one per line). Click **Prepare
application** to send the workspace's confirmed profile facts, job description,
preferences, and instructions to the configured Groq model.

The UI shows the role analysis, coordinator decisions, draft materials, evidence,
review findings, and activity. If questions appear, answer each or enter
`unknown`, confirm that the answers can be used in the drafts, then continue.
These are run-specific confirmations; they do not modify your Career Profile.
Completed materials are saved as workspace draft versions. Always inspect them
before use; the reviewer is a model and cannot guarantee correctness. No automatic
submission, external job search, notification scheduling, or email runs here.

## Agents and routing

- **Analyst** identifies requirements with numbered job passage references,
  matches candidate fact IDs, identifies missing facts, and extracts screening
  questions present verbatim in the job description.
- **Coordinator** chooses among the actions allowed at the current stage:
  clarify, write, revise, reject, or finish. The decision and reason are visible.
- **Writer** creates a cover letter, supported resume suggestions, and available
  screening answers with candidate fact references. Unknown answers remain null.
- **Reviewer** independently evaluates factual support, relevance, and completeness,
  recording artifact-specific informational, warning, and blocking findings.

The graph starts with analysis and coordination. Clarification uses a durable
LangGraph interrupt. Answers return to analysis with new run-specific source IDs.
Writing is followed by persistence, review, finding persistence, and coordination.
Rejected roles stop with an explanation without changing the manual job tracker.
`ready_for_review` means model-reviewed drafts awaiting the human, not approval or
submission. `needs_review` means unresolved blocking findings remain at the limit.

There are at most three Writer passes and two clarification rounds per run.
The coordinator cannot finish before review, finish with blocking findings, or
request actions outside the current budget. Invalid source IDs, invented or
omitted screening questions, and unsupported resume suggestions fail validation.
The backend resolves job reference IDs into original text spans; it does not ask
the model to reproduce long evidence quotes. ID validation does not establish
semantic entailment: the Reviewer and human still assess whether sources support
claims. Greetings and nonfactual cover-letter prose may have no source IDs.

## Persistence and recovery

Application runs use `workflow=application_v1` in the existing run table. Additive
migrations retain earlier `setup_v1` runs and checkpoints. The graph implementation
is selected using the saved workflow version; setup runs remain available under
the legacy setup section.

Each node has a SQLite checkpoint. Model failures return the run ID, saved phase,
pending node, and a retryable error. Reopen the run and use **Retry failed step**;
only the pending node executes again. Draft persistence follows a checkpointed
Writer result and uses stable run/pass/artifact request IDs, so restart recovery
does not create duplicate drafts. Findings similarly use stable run/pass/index
keys. Drafts remain linked to the immutable workspace profile version.

Resume requests carry the current checkpoint ID and one answer per question.
Stale input is rejected. Already-consumed answers have a saved token and payload
hash, so identical retries do not answer a later question by mistake. Start retries
with the same request ID return the existing run; failure recovery then uses the
retry endpoint. A changed start payload needs a new request ID.

Per-run process locks prevent overlapping executions. Cloud tracing remains
disabled. A single HTTP request drives the graph until it pauses, fails, or finishes;
it may take several minutes. This version has no background worker or live event
stream. Saved runs can be reopened after request or backend interruptions.

## API additions

All writes require the existing local-request header.

- `POST /api/workspaces/{id}/agent-runs`:
  `{request_id, instructions?, screening_questions?}`.
- `GET /api/workspaces/{id}/runs/{run_id}`: shared inspection endpoint.
- `POST /api/workspaces/{id}/agent-runs/{run_id}/resume`:
  `{checkpoint_id, answers: [...]}`.
- `POST /api/workspaces/{id}/agent-runs/{run_id}/retry`:
  `{checkpoint_id}`.

Run state contains the input snapshot, analysis, package, reviews, decisions,
clarifications, draft IDs, budgets, and activity. Full state is private local data.

## Verification

Deterministic tests mock the specialist boundary while exercising real graphs,
SQLite checkpoints, and API handlers. They cover completion, clarification and
idempotent resume, rejection, revision limits, invalid coordinator actions,
unknown fact IDs, missing screening questions, and recovery from Reviewer failure
without repeating Writer or duplicating drafts. UI tests cover explicit answer
confirmation, displaying output, reopening runs, and retrying failed steps.

### Live integration observation

A diagnostic using synthetic candidate/job facts and the configured Groq provider
completed analysis, drafting, review, and a coordinator-directed revision. It
created two sets of draft artifacts, then hit a provider rate limit at the next
Reviewer step. The response correctly identified the pending Reviewer node and
returned a recoverable error. This was temporary diagnostic storage, not a user's
application workspace, and is not evidence of a successful end-to-end live run.
No saved user resume or profile was transmitted for this diagnostic.
