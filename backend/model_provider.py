"""Explicit Groq/local Ollama selection; no automatic provider fallback."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from langchain_core.runnables import RunnableLambda


def provider():
    load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
    selected = os.environ.get('LLM_PROVIDER', 'groq').strip().lower()
    if selected not in ('groq', 'ollama'):
        raise HTTPException(503, 'Set LLM_PROVIDER to groq or ollama in backend/.env, then restart.')
    return selected


def local_settings():
    provider()
    model = os.environ.get('OLLAMA_MODEL', 'qwen3:8b').strip()
    base = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434').strip().rstrip('/')
    try:
        url = urlsplit(base)
        if (url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1', '::1')
                or url.username or url.password or url.path or url.query or url.fragment):
            raise ValueError()
        port = url.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        context = int(os.environ.get('OLLAMA_NUM_CTX', '32768'))
        timeout = float(os.environ.get('OLLAMA_TIMEOUT_SECONDS', '180'))
        if not model or not 4096 <= context <= 131072 or not 1 <= timeout <= 600:
            raise ValueError()
    except ValueError as error:
        raise HTTPException(503, 'Check Ollama configuration: use a local HTTP origin, a model name, OLLAMA_NUM_CTX 4096–131072, and timeout 1–600 seconds.') from error
    return {'model': model, 'base': base, 'context': context, 'timeout': timeout}


def metadata():
    if provider() == 'ollama':
        settings = local_settings()
        return {'provider': 'Ollama (local)', 'model': settings['model'], 'configured': True,
                'supported_models': [], 'local': True}
    from qa import configuration, SUPPORTED_MODELS
    key, model = configuration()
    return {'provider': 'Groq', 'model': model, 'configured': bool(key) and model in SUPPORTED_MODELS,
            'supported_models': list(SUPPORTED_MODELS), 'local': False}


def cooldown_model():
    if provider() == 'ollama':
        return 'ollama:' + local_settings()['model']
    from qa import configuration
    return configuration()[1]  # Retain existing persisted Groq cooldown keys.


def saved_cooldown(progress):
    # Older batches did not name the provider; their retry timestamps are Groq's.
    return progress.get('retry_at') if progress.get('retry_provider', 'groq') == provider() else None


def ollama_model(schema, max_tokens):
    settings = local_settings()
    def invoke(messages):
        if hasattr(messages, 'to_messages'):
            messages = messages.to_messages()
        normalized = []
        for message in messages:
            if isinstance(message, tuple):
                role, content = message
            else:
                role, content = message.type, message.content
            role = {'human': 'user', 'ai': 'assistant'}.get(role, role)
            normalized.append({'role': role, 'content': content})
        normalized.insert(0, {'role': 'system', 'content': 'Return only JSON matching this schema: ' + json.dumps(schema.model_json_schema())})
        payload = {'model': settings['model'], 'messages': normalized, 'stream': False,
                   'format': schema.model_json_schema(), 'think': False,
                   'options': {'temperature': 0, 'num_ctx': settings['context'], 'num_predict': max_tokens}}
        try:
            # Ignore proxy environment variables and redirects: resume data stays local.
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=settings['timeout']) as client:
                response = client.post(settings['base'] + '/api/chat', json=payload)
            if response.status_code == 404:
                raise HTTPException(503, f'Ollama model is unavailable. Run ollama pull {settings["model"]}, then retry the saved step.')
            if response.status_code == 429:
                from provider_limits import GUARD, retry_seconds
                guard = GUARD.get()
                if guard:
                    guard.limited(cooldown_model(), response.headers)
                raise HTTPException(429, 'Ollama is busy. Progress is saved; resume manually later.', headers={'Retry-After': str(retry_seconds(response.headers))})
            if response.status_code >= 300:
                raise HTTPException(502, 'Ollama rejected the request. Check its model, available memory and context settings; saved work is preserved.')
            result = response.json()
            if not isinstance(result, dict) or not result.get('done') or result.get('done_reason') == 'length':
                raise ValueError('Incomplete response')
            return schema.model_validate_json(result['message']['content'])
        except HTTPException:
            raise
        except httpx.TimeoutException as error:
            raise HTTPException(504, 'Ollama took too long. Progress is saved; retry manually or increase OLLAMA_TIMEOUT_SECONDS.') from error
        except httpx.RequestError as error:
            raise HTTPException(503, 'Cannot reach local Ollama. Open the Ollama app or run ollama serve, then retry the saved step.') from error
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(502, 'Ollama returned an incomplete or invalid structured response. Saved work is preserved; retry manually or try a more capable local model.') from error
    return RunnableLambda(invoke)
