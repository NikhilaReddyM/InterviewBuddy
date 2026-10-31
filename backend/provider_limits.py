"""Persist provider cooldowns without storing credentials or request content."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re
import time

from fastapi import HTTPException

GUARD = ContextVar('application_provider_guard', default=None)


def retry_seconds(headers):
    headers = {str(key).lower(): value for key, value in headers.items()}
    value = headers.get('retry-after', '')
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            # Groq reset headers use durations such as 1m20.5s.
            duration = headers.get('x-ratelimit-reset-tokens', '')
            parts = re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h)', duration)
            seconds = sum(float(number) * {'ms': .001, 's': 1, 'm': 60, 'h': 3600}[unit] for number, unit in parts) if parts else 60
    return max(1, math.ceil(seconds)) if math.isfinite(seconds) else 60


class ProviderGuard:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS provider_cooldowns (model TEXT PRIMARY KEY, retry_at REAL NOT NULL)')

    def before_call(self, model):
        with self.store.connect() as db:
            row = db.execute('SELECT retry_at FROM provider_cooldowns WHERE model=?', (model,)).fetchone()
        if row and row['retry_at'] > time.time():
            self.pause(math.ceil(row['retry_at'] - time.time()))

    def limited(self, model, headers):
        seconds = retry_seconds(headers)
        with self.store.connect() as db:
            db.execute('INSERT INTO provider_cooldowns VALUES (?,?) ON CONFLICT(model) DO UPDATE SET retry_at=MAX(retry_at,excluded.retry_at)', (model, time.time() + seconds))
        self.pause(seconds)

    @staticmethod
    def pause(seconds):
        raise HTTPException(429, 'The model provider is temporarily throttling requests. Progress is saved; resume manually after the cooldown.',
                            headers={'Retry-After': str(seconds)})


@contextmanager
def provider_guard(store):
    token = GUARD.set(ProviderGuard(store))
    try:
        yield
    finally:
        GUARD.reset(token)


def retry_at(seconds):
    return datetime.fromtimestamp(time.time() + seconds, timezone.utc).isoformat()
