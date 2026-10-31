"""Bounded public job-feed readers; no resume information is sent to job boards."""
from datetime import datetime, timezone
from html.parser import HTMLParser
from html import unescape
import os
from pathlib import Path
import re
import json
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import httpx

SOURCES = {'remotive': 'https://remotive.com/api/remote-jobs',
           'arbeitnow': 'https://www.arbeitnow.com/api/job-board-api'}


DEFAULT_GREENHOUSE = 'datadog,mongodb,cloudflare'
DEFAULT_ASHBY = 'ramp,notion'


def source_registry():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
    result = dict(SOURCES)
    for provider, default in [('greenhouse', DEFAULT_GREENHOUSE), ('ashby', DEFAULT_ASHBY)]:
        tokens = os.environ.get(provider.upper() + '_BOARDS', default).split(',')
        for token in list(dict.fromkeys(value.strip() for value in tokens if value.strip()))[:6]:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', token):
                continue
            result[f'{provider}:{token}'] = (f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true'
                if provider == 'greenhouse' else f'https://api.ashbyhq.com/posting-api/job-board/{token}')
    return result


def workplace(value='', location='', description='', remote=None):
    value = str(value or '').casefold().replace('-', '')
    if value in ('hybrid', 'remote', 'onsite'):
        return value
    # Explicit title/location/metadata is stronger evidence than generic benefits.
    location = str(location).casefold()
    if 'hybrid' in location:
        return 'hybrid'
    if 'remote' in location:
        return 'remote'
    if 'on-site' in location or 'onsite' in location:
        return 'onsite'
    description = str(description).casefold()
    if re.search(r'\bhybrid (?:workplace|work (?:model|schedule|arrangement)|working (?:model|arrangement)|role|position)\b', description):
        return 'hybrid'
    if re.search(r'\b(?:fully remote|100% remote|this (?:role|position) is remote)\b', description):
        return 'remote'
    if remote is True:
        return 'remote'
    return 'unknown'


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'br', 'li', 'div', 'h1', 'h2', 'h3'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'li', 'div'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    parser = TextParser()
    parser.feed(unescape(unescape(str(value or '')[:150000])))
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())[:30000]


def safe_url(url):
    try:
        parsed = urlsplit(str(url))
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            return ''
        query = urlencode([(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith('utm_') and key.lower() not in ('gh_src', 'tracking')])
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip('/'), query, ''))
    except ValueError:
        return ''


def fetch_feed(source):
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        with client.stream('GET', source_registry()[source], headers={'User-Agent': 'InterviewBuddy/1.0 personal-job-search'}) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 12 * 1024 * 1024:
                    raise ValueError('Job feed exceeded the size limit.')
    payload = json.loads(body)
    rows = payload.get('data' if source == 'arbeitnow' else 'jobs')
    if not isinstance(rows, list):
        raise ValueError('Unexpected job feed format.')
    jobs = []
    for row in rows[:1000]:
        if not isinstance(row, dict):
            continue
        provider = source.split(':')[0]
        board = source.split(':', 1)[1] if ':' in source else ''
        if provider == 'ashby' and row.get('isListed') is False:
            continue
        if provider == 'greenhouse' and row.get('internal_job_id', 'unknown') is None:
            continue  # Prospect/talent-pool posts are not openings.
        url = safe_url(row.get('absolute_url') if provider == 'greenhouse' else row.get('applyUrl') or row.get('jobUrl') if provider == 'ashby' else row.get('url', ''))
        company = str(row.get('company_name') or board)[:300]
        role = str(row.get('title', ''))[:300]
        description = plain_text(row.get('content') if provider == 'greenhouse' else row.get('descriptionPlain') or row.get('descriptionHtml') if provider == 'ashby' else row.get('description', ''))
        location = row.get('location', '')
        if isinstance(location, dict):
            location = location.get('name', '')
        countries = []
        if provider == 'greenhouse':
            locations = [location] + [office.get('location', '') for office in row.get('offices', [])]
            location = '; '.join(dict.fromkeys(value for value in locations if value))
            metadata = row.get('metadata') or []
            mode_hint = next((entry.get('value', '') for entry in metadata if isinstance(entry, dict) and any(term in str(entry.get('name', '')).lower() for term in ('workplace', 'work location', 'work type'))), '')
            mode = workplace(mode_hint, location, description)
        elif provider == 'ashby':
            address = row.get('address', {}) or {}
            postal = address.get('postalAddress', address) or {}
            countries = [postal.get('addressCountry', '')]
            secondary = row.get('secondaryLocations') or []
            countries += [(entry.get('address') or {}).get('addressCountry', '') for entry in secondary]
            location = '; '.join(dict.fromkeys(str(value) for value in [location, *[entry.get('location', '') for entry in secondary], *countries] if value))
            mode = workplace(row.get('workplaceType', ''), location)
        else:
            location = str(row.get('candidate_required_location', location or 'Unspecified'))
            mode = workplace(location=location, remote=True if provider == 'remotive' else row.get('remote'))
        if not url or not company.strip() or not role.strip() or not description.strip():
            continue
        jobs.append({'source': source, 'source_id': str(row.get('id', row.get('slug', url)))[:500],
            'url': url, 'company': company, 'role': role, 'description': description,
            'location': str(location or 'Unspecified')[:1500], 'workplace': mode, 'remote': mode == 'remote',
            'published_at': str(row.get('publication_date') or row.get('publishedAt') or row.get('updated_at') or row.get('created_at') or '')[:100],
            'retrieved_at': datetime.now(timezone.utc).isoformat()})
    return jobs


def cached_feed(store, source):
    timestamp = datetime.now(timezone.utc).timestamp()
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS job_feed_cache (source TEXT PRIMARY KEY, fetched REAL, payload TEXT, error TEXT)')
        cached = db.execute('SELECT * FROM job_feed_cache WHERE source=?', ('v2:' + source,)).fetchone()
    if cached and timestamp - cached['fetched'] < (21600 if not cached['error'] else 600):
        if cached['error']:
            raise ValueError(cached['error'])
        return json.loads(cached['payload'])
    try:
        jobs = fetch_feed(source)
    except Exception as error:
        message = f'{source} could not be reached or returned invalid data. Other sources may still work.'
        with store.connect() as db:
            db.execute('INSERT OR REPLACE INTO job_feed_cache VALUES (?,?,?,?)', ('v2:' + source, timestamp, '[]', message))
        raise ValueError(message) from error
    with store.connect() as db:
        db.execute('INSERT OR REPLACE INTO job_feed_cache VALUES (?,?,?,NULL)', ('v2:' + source, timestamp, json.dumps(jobs)))
    return jobs
