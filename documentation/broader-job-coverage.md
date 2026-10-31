# Broader public job coverage

## Try it without model quota

Restart the backend and refresh the app. In **Find Opportunities**, use the new
**Browse public job listings** section at the top:

1. Enter role keywords (for example `software engineer` or `staff engineer`).
2. Choose `US`, `Europe`, or a city, and a work arrangement.
3. Click **Browse jobs — no AI**.
4. Inspect source coverage, original links, and job descriptions.
5. Choose a confirmed resume profile and **Save job for later** to create a workspace.

Browsing and saving do not call Groq, analyze your resume, or generate application
materials. A profile is not needed to browse. Saving uses a confirmed profile
snapshot and a stable resume/URL request key to prevent duplicate workspace writes.
Full AI matching and application generation still require provider quota.

## Supported sources

Existing Remotive and Arbeitnow feeds are retained. Five selected employer boards
are now enabled by default:

| Provider | Default employer boards |
|---|---|
| Greenhouse | Datadog, MongoDB, Cloudflare |
| Ashby | Ramp, Notion |

These are selected companies, not every job hosted on either platform. They add
US, hybrid, on-site, and international roles. The Muse was evaluated but not added;
its documented registration requirements differ from these public employer reads.

[Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html) provides public
GET access to published jobs, descriptions, locations, and application URLs.
[Ashby's public postings API](https://developers.ashbyhq.com/docs/public-job-posting-api)
provides listed openings and explicit workplace types when available. Ashby's
`isRemote` can also be true for hybrid jobs; the adapter uses `workplaceType`
instead of incorrectly treating every such role as fully remote.

Configure company-board slugs in ignored `backend/.env`:

```dotenv
GREENHOUSE_BOARDS=datadog,mongodb,cloudflare
ASHBY_BOARDS=ramp,notion
```

Restart after changing configuration. Comma-separated slugs are validated and
capped at six per provider. Empty values disable that provider's company boards.
Only the fixed Greenhouse and Ashby API host patterns are used; arbitrary source
URLs are not accepted. A provider can migrate a company's board over time, so
unavailable boards appear as source errors while the others continue.

## Normalization and matching

Adapters convert employer HTML into plain text, omit unlisted/talent-pool posts,
preserve application identifiers such as `gh_jid`, and retain source and retrieval
timestamps. Sources use bounded requests and six-hour success caches; failures
have a ten-minute cache. No candidate information is sent to job boards.

Workplace mode uses explicit fields or location labels, plus narrow explicit
hybrid/fully-remote phrases in Greenhouse descriptions. Unspecified mode stays
`unknown` rather than being labeled on-site. Verify the arrangement in the original
posting. Browse filters include unknown mode separately so their behavior is clear.

The AI discovery path uses the same configured sources. Before sending at most
12 candidates to the Matcher, the local shortlist boosts preference-aligned
locations and known workplace types and excludes explicit work-mode conflicts.
Unknown workplace types remain eligible for model assessment. US/Europe aliases
and common US cities are supported; location matching is a convenience filter,
not an exhaustive geography or work-authorization determination. Employer country
and regional restrictions still need final review.

Source expansion applies to new searches and catalog browsing. Resuming an old
batch or reassessing its saved jobs preserves the old listing set intentionally.
Start a fresh discovery batch when you want the newly added sources included.
Groq retries remain manual; recurring discovery is available through explicitly enabled [schedule settings](scheduled-discovery.md).

## API and validation

`GET /api/job-catalog?q=software%20engineer&location=US&workplace=hybrid&limit=50`
returns normalized jobs, source counts/errors, total matches, and `model_calls: 0`.
Limits are 1–100 results, and accepted work modes are any/remote/hybrid/onsite/unknown.
It makes no model calls and does not require a resume or an additional API key.

Tests cover both new adapters, encoded HTML safety, functional application URL
queries, public/unlisted records, hybrid-vs-remote distinction, unknown modes,
source configuration validation, model-free filtering, location ranking, and
browsing/saving in the UI. Live public-feed checks confirmed that all five default
employer boards return listings, including US hybrid openings. No user resume or
model provider was involved in those live checks.
