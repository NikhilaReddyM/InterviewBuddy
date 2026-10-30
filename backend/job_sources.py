"""Bounded public job-feed readers; no resume information is sent to job boards."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from urllib.parse import urlsplit, urlunsplit

import httpx

SOURCES = {'remotive': 'https://remotive.com/api/remote-jobs',
           'arbeitnow': 'https://www.arbeitnow.com/api/job-board-api'}


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
    parser.feed(str(value or '')[:150000])
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())[:30000]


def safe_url(url):
    try:
        parsed = urlsplit(str(url))
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            return ''
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip('/'), '', ''))
    except ValueError:
        return ''


def fetch_feed(source):
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        with client.stream('GET', SOURCES[source], headers={'User-Agent': 'InterviewBuddy/1.0 personal-job-search'}) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 12 * 1024 * 1024:
                    raise ValueError('Job feed exceeded the size limit.')
    payload = json.loads(body)
    rows = payload.get('jobs' if source == 'remotive' else 'data')
    if not isinstance(rows, list):
        raise ValueError('Unexpected job feed format.')
    jobs = []
    for row in rows[:1000]:
        if not isinstance(row, dict):
            continue
        url = safe_url(row.get('url', ''))
        company = str(row.get('company_name', ''))[:300]
        role = str(row.get('title', ''))[:300]
        description = plain_text(row.get('description', ''))
        if not url or not company.strip() or not role.strip() or not description.strip():
            continue
        jobs.append({'source': source, 'source_id': str(row.get('id', row.get('slug', url)))[:500],
            'url': url, 'company': company, 'role': role, 'description': description,
            'location': str(row.get('candidate_required_location', row.get('location', 'Unspecified')))[:1000],
            'remote': True if source == 'remotive' else bool(row.get('remote', False)),
            'published_at': str(row.get('publication_date', row.get('created_at', '')))[:100],
            'retrieved_at': datetime.now(timezone.utc).isoformat()})
    return jobs


def cached_feed(store, source):
    timestamp = datetime.now(timezone.utc).timestamp()
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS job_feed_cache (source TEXT PRIMARY KEY, fetched REAL, payload TEXT, error TEXT)')
        cached = db.execute('SELECT * FROM job_feed_cache WHERE source=?', (source,)).fetchone()
    if cached and timestamp - cached['fetched'] < (21600 if not cached['error'] else 600):
        if cached['error']:
            raise ValueError(cached['error'])
        return json.loads(cached['payload'])
    try:
        jobs = fetch_feed(source)
    except Exception as error:
        message = f'{source} could not be reached or returned invalid data. Other sources may still work.'
        with store.connect() as db:
            db.execute('INSERT OR REPLACE INTO job_feed_cache VALUES (?,?,?,?)', (source, timestamp, '[]', message))
        raise ValueError(message) from error
    with store.connect() as db:
        db.execute('INSERT OR REPLACE INTO job_feed_cache VALUES (?,?,?,NULL)', (source, timestamp, json.dumps(jobs)))
    return jobs
