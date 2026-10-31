# Model providers

InterviewBuddy supports an explicit backend choice of Groq or local Ollama for
Career Profile generation, discovery planning/matching, Analyst/Writer/Reviewer/
Coordinator, and cited PDF Q&A. Existing stored profiles, checkpoints, drafts and
reminders are retained. No additional Python dependency is required.

## Use local Qwen

Install and open Ollama, then download the model:

```sh
ollama pull qwen3:8b
ollama list
```

Add or update these settings in ignored `backend/.env`:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_NUM_CTX=32768
OLLAMA_TIMEOUT_SECONDS=180
```

Restart the Python backend and refresh the app. Ollama must stay running. If the
app is closed, `ollama serve` can start the local server (do not start a second
server if one is already running). No Ollama API key is needed. The Python virtual
environment can remain active.

First test a single saved application workspace with **Prepare application** or
**Retry failed step**. You can also **Resume saved batch** to continue discovery
without replaying successful groups. The next unfinished step uses the configured
provider; earlier saved results retain their original content and profile version.
To regenerate completed work with the latest profile, use reassessment instead.
Provider changes do not automatically start or resume old batches. Enabled future
discovery schedules use the selected provider after backend restart.

Start with one application per discovery run: local generation may take longer
than hosted inference. A Groq cooldown does not block Ollama. Local model calls
have no hosted token quota, but context, output size, memory and time limits still
apply. Increasing context consumes additional RAM; try a more capable model when
output quality is inadequate, then review the generated claims yourself.

The Q&A **Sources & model** panel shows the configured provider/model. Discovery
activity records the provider/model used by each processing invocation.
`GET /api/qa/config` reports configuration, not a live connectivity guarantee.

## Switch back to Groq

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=your-key
GROQ_MODEL=openai/gpt-oss-120b
```

Restart the backend. Existing process environment variables take precedence over
`.env`, so remove an exported `LLM_PROVIDER` if it overrides the file. With no
provider setting, Groq remains the default. No automatic cross-provider fallback
or repeated cooldown retries are performed.

## Validation, privacy and recovery

The native Ollama `/api/chat` request uses the existing Pydantic JSON schemas,
nonstreaming responses, temperature zero and `think: false` for Qwen3. The same
fact IDs, source references, citation checks, reviewer and checkpoint logic still
run. Structured JSON does not prove factual correctness.

Only loopback HTTP origins are accepted for Ollama. Redirects and environment
proxies are disabled for those requests. No inference prompts are sent to Groq
when Ollama is selected. Discovery still reads public job sources on the internet;
email still uses the separately configured SMTP server. Cloud tracing remains off.

An unavailable server, missing model, timeout, invalid/truncated response or
provider rejection produces a safe actionable error. No raw provider response or
private prompt is displayed. Resume the saved step manually after resolving it.
Profile evidence correction retains its existing maximum of two attempts; there
is no automatic provider fallback or network retry loop.

References: [Ollama chat API](https://docs.ollama.com/api/chat) and
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Local validation observation

A live diagnostic on the installed `qwen3:8b` model used only synthetic candidate
and job data in temporary storage. Search planning returned valid structured
output in 1.95 seconds, and profile extraction produced three source-backed facts
in 3.74 seconds. The complete Analyst/Coordinator/Writer/Reviewer graph reached
`ready_for_review` in 20.18 seconds and saved three draft artifacts. Reopening the
same run retained the same run ID and three drafts. These small diagnostics do
not establish quality or latency for a real resume or a large discovery batch.
No real application, email or cloud-model request was made by these diagnostics.
