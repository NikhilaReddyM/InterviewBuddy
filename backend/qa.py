"""Week 2 cited Q&A: hybrid retrieval -> LangChain -> Groq -> citation checks."""
import os
import threading
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from fastapi import HTTPException
from pydantic import BaseModel, Field

from qa_contract import AnswerDraft
from qa_pipeline import answer_from_retrieval

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ('Dynamic Programming.pdf', 'Dynamic Programming Part 9.pdf',
          'Dynamic Programming Series Part 10 Slides.pdf')
DEFAULT_MODEL = 'openai/gpt-oss-120b'
SUPPORTED_MODELS = (DEFAULT_MODEL, 'openai/gpt-oss-20b')
GENERATION_LOCK = threading.Lock()


def configuration():
    # Backend-only credentials. Existing process environment wins over the local file.
    load_dotenv(ROOT / 'backend/.env', override=False)
    return os.environ.get('GROQ_API_KEY', '').strip(), os.environ.get('GROQ_MODEL', DEFAULT_MODEL).strip()


def structured_model():
    key, model_id = configuration()
    if not key or model_id not in SUPPORTED_MODELS:
        raise HTTPException(503, 'Configure GROQ_API_KEY and a supported GROQ_MODEL in backend/.env, then restart the backend.')
    from langchain_groq import ChatGroq
    return ChatGroq(model=model_id, api_key=key, base_url='https://api.groq.com',
                    temperature=0, timeout=45, max_retries=0, max_tokens=4096).with_structured_output(
                        AnswerDraft, method='json_schema', strict=True)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


def register(app, connect, retrieve, search_type):
    def corpus():
        db = connect()
        try:
            result = []
            for filename in CORPUS:
                matches = db.execute('SELECT id,filename,status FROM documents WHERE filename=?', (filename,)).fetchall()
                if len(matches) != 1:
                    raise HTTPException(409, f'Import exactly one active copy of {filename} before asking questions. Multiple imported versions must be resolved first.')
                result.append(dict(matches[0]))
            return result
        finally:
            db.close()

    @app.get('/api/qa/config')
    def settings():
        key, model_id = configuration()
        try:
            docs = corpus()
            corpus_error = None
        except HTTPException as error:
            docs, corpus_error = [], error.detail
        return {'provider': 'Groq', 'model': model_id or None,
                'configured': bool(key) and model_id in SUPPORTED_MODELS,
                'supported_models': list(SUPPORTED_MODELS), 'documents': docs, 'corpus_error': corpus_error,
                'retrieval': 'hybrid', 'include_unreviewed': True, 'tracing': False}

    @app.post('/api/qa/ask')
    def ask(request: Question):
        if not request.question.strip():
            raise HTTPException(422, 'Enter a question.')
        key, model_id = configuration()
        if not key or model_id not in SUPPORTED_MODELS:
            raise HTTPException(503, 'Set GROQ_API_KEY and GROQ_MODEL in backend/.env, then restart the backend. Never put your API key in the browser.')
        if not GENERATION_LOCK.acquire(blocking=False):
            raise HTTPException(409, 'An answer is already being generated. Wait for it to finish.')
        started = perf_counter()
        try:
            docs = corpus()
            retrieval = retrieve([d['id'] for d in docs], search_type(
                query=request.question, method='hybrid', top_k=5, group_pages=False))
            model = structured_model() if retrieval['results'] else None
            result = answer_from_retrieval(request.question, retrieval, model)
            return {**result, 'question': request.question, 'provider': 'Groq', 'model': model_id,
                    'retrieval_method': 'hybrid', 'elapsed_ms': round((perf_counter() - started) * 1000, 2),
                    'citation_validation': 'Source IDs and exact quotes checked; claim support still needs human review.',
                    'index_snapshots': retrieval.get('index_snapshots', [])}
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(502, 'The model response failed citation or output validation. No unvalidated answer was displayed. Try rephrasing the question.') from error
        except Exception as error:
            from groq import AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError
            if isinstance(error, AuthenticationError):
                raise HTTPException(503, 'Groq rejected the API key. Check backend/.env and restart.') from error
            if isinstance(error, RateLimitError):
                raise HTTPException(429, 'Groq rate limit reached. Wait before asking again.') from error
            if isinstance(error, APITimeoutError):
                raise HTTPException(504, 'Groq took too long to respond. Please retry later.') from error
            if isinstance(error, APIConnectionError):
                raise HTTPException(503, 'Could not reach Groq. Check your internet connection.') from error
            # Avoid logging provider exception bodies, prompts, excerpts, or credentials.
            raise HTTPException(502, 'Groq could not produce a valid answer. Check your model access or try again later.') from error
        finally:
            GENERATION_LOCK.release()
