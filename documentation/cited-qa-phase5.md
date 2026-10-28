# Phase 5: cited Q&A (Week 2 scope)

## Implemented scope

Detailed, source-grounded answers over the three Dynamic Programming PDFs, using existing local hybrid retrieval, a LangChain prompt/model/validation chain, and Groq-hosted generation. Unreviewed source text is included with visible labels. No LangGraph workflow or hosted tracing is configured; systematic evaluation and LangSmith can be revisited in Week 4.

Generation is configurable. Supported strict-structured-output models are `openai/gpt-oss-120b` and `openai/gpt-oss-20b`. Despite the model IDs, the configured inference endpoint is Groq, not OpenAI. The selected starting model is `openai/gpt-oss-120b`; `GROQ_MODEL` can override it. This choice was made after the user authorized selecting a model.

## Setup

1. Update the backend environment:

```sh
backend/.venv/bin/pip install -r backend/requirements.lock.txt
```

2. Create a Groq API key in your account at https://console.groq.com/keys. Model access and rate limits depend on your account.
3. Copy the configuration template (only if you do not already have a backend environment file):

```sh
cp backend/.env.example backend/.env
```

4. Edit `backend/.env` locally. Add your key and explicitly choose a model:

```dotenv
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

You can instead choose `openai/gpt-oss-20b`. Never paste a real key into chat, frontend code, `VITE_*` variables, or a tracked file. `backend/.env` is ignored; `.env.example` contains no secrets. Existing process environment variables override the local environment file.

5. Restart the backend and run the frontend in separate terminals:

```sh
backend/.venv/bin/python backend/documents.py serve
```

```sh
npm run dev
```

6. Open Resources & Revision → Open PDF library → Ask my PDFs. Enter a question, then select Ask with citations. Each click makes a real Groq generation request if configured. Questions and the selected text excerpts leave your laptop; originals, page images, local embeddings, and the full PDFs are not uploaded by this flow.

## Required local corpus

Exactly one imported copy of each file must exist:

- Dynamic Programming.pdf
- Dynamic Programming Part 9.pdf
- Dynamic Programming Series Part 10 Slides.pdf

All three indexes must be current. If text or review state changes, rebuild the affected index before asking. Multiple versions with the same filename require resolving the corpus choice; the app does not silently select one. For Week 2 the corpus is fixed to these three files; broader document selection can be added later.

## Answer behavior

1. Retrieve five passages using the existing hybrid retriever across all three documents.
2. Assign request-local source IDs (S1, S2, …). Include text and review status in the model prompt.
3. Use LangChain `ChatPromptTemplate` and `ChatGroq` strict JSON-schema output.
4. Validate output with Pydantic. Each answer section must cite known source IDs and exact evidence quotes, allowing whitespace normalization.
5. Build filename/page URLs from backend metadata, never model-generated URLs.
6. Display detailed sections, per-section citations, original-PDF links, review labels, and an explicit missing-evidence notice when appropriate.

Clicking a section citation expands the retrieved-sources panel and focuses its source; original PDF links open the matching physical page. Evidence quotes appear in section details. Sources may contain OCR mistakes, and citation-ID/quote validation does not prove that the explanation follows logically from the passage. No automatic faithfulness score is claimed.

The model is instructed to use only provided excerpts, ignore embedded instructions, avoid inventing code/formulas/complexity claims, and acknowledge incomplete evidence. An empty retrieval returns a missing-evidence response without a model invocation. API failures are errors, never disguised as missing evidence. Invalid citations or structured output produce an error; the unvalidated answer is not displayed.

The provider has a 45-second request timeout, no automatic SDK retries, a 4096-output-token cap, and a single concurrent generation per backend process. These are implementation bounds, not a measured latency/cost guarantee. Refusals, malformed/truncated responses, and model-access failures may require rephrasing or checking configuration. Requests and answers are not saved as conversation history. There is no automatic question replay or fallback provider.

## Prompt and structured contract

- `backend/qa_contract.py`: versioned system prompt, Pydantic schema, source construction, citation checks.
- `backend/qa_pipeline.py`: LangChain answer chain, with tracing explicitly disabled.
- `backend/qa.py`: Groq adapter, configuration, fixed corpus, and API endpoints.

Model output contains sections (title, text, source IDs and exact quotes), an insufficient-evidence boolean, and a missing-information explanation. Backend responses add trusted source metadata, timings, model/provider, and index snapshots. This is structured answer output; `dp-questions.json` remains separate evaluation input.

## Verification and manual demo

Only mocked generation tests were authorized and run. No Groq generation calls were made during implementation. Tests exercise the real LangChain composition with a fake structured model and cover citations, fabricated references/quotes, missing evidence, provider setup, and UI source navigation. Hosted answer quality, actual token cost, and live latency have not been measured.

Try these manually after configuring Groq:

- Ask how memoization differs from tabulation; inspect the returned evidence and original pages.
- Ask a problem-specific question, such as the restriction in House Robber II.
- Ask for your interview date; verify that the assistant acknowledges missing evidence rather than inferring it from unrelated passages.

Record which claims are supported and any OCR/retrieval failures. This small sanity check is enough to inform the Week 2 demo; systematic grading and tracing remain Week 4 work.

References checked during implementation:

- https://console.groq.com/docs/structured-outputs
- https://reference.langchain.com/python/langchain-groq/chat_models/ChatGroq/with_structured_output
