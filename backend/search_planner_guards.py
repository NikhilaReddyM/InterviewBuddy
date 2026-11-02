"""Bounded output guards for search terms; not a general semantic safety classifier."""
import re
import unicodedata

VERSION = 'planner-guards-v1'
EMAIL = re.compile(r'[\w.!#$%&\x27*+/=?^`{|}~-]+\s*@\s*[\w.-]+', re.UNICODE)
URL = re.compile(r'(?:https?://|www\.)\S+', re.I)
PHONE = re.compile(r'(?<!\w)\+?\d[\d ()-]{5,}\d(?!\w)')
COMMAND = re.compile(r'\b(ignore|instructions?|system prompt|return only|copy my|override)\b', re.I)
ALIASES = {
    'qa': ('qa', 'quality assurance', 'pytest', 'selenium', 'automated tests', 'automated testing', 'test automation', 'automation'),
    'test automation': ('test automation', 'pytest', 'selenium', 'automated tests', 'automated testing', 'automation'),
    'management': ('management', 'manager', 'managing'),
}


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def contains(text, term):
    return bool(re.search(r'(?<!\w)' + re.escape(normalized(term)) + r'(?!\w)', normalized(text)))


def has_identifier(text):
    return bool(EMAIL.search(text) or URL.search(text) or PHONE.search(text))


def excluded_terms(preferences):
    text = preferences.get('exclusions', '')
    # Commands in a data field must not become output-filter policy.
    if COMMAND.search(text):
        return []
    terms = []
    for fragment in re.split(r'[,;\n]|\band\b|\bor\b', normalized(text)):
        term = re.sub(r'\b(?:roles?|jobs?|positions?|only)\b', '', fragment).strip(' .')
        if not term:
            continue
        terms.extend(ALIASES.get(term, (term,)))
    return list(dict.fromkeys(terms))


def conflicting_skills(facts):
    statements = [f.get('text', '') for f in facts.values()]
    conflicts = []
    pattern = re.compile(r'\b(?:do not have|don\x27t have|no|lack)\s+([\w+#. -]{1,60}?)\s+experience\b', re.I)
    for i, statement in enumerate(statements):
        for match in pattern.finditer(statement):
            skill = match.group(1).strip()
            if any(i != j and not pattern.search(other) and contains(other, skill)
                   for j, other in enumerate(statements)):
                conflicts.append(skill)
    return list(dict.fromkeys(conflicts))


def guard_plan(plan, context):
    preferences = context.get('preferences', {})
    facts = context.get('facts', {})
    excluded = excluded_terms(preferences)
    conflicts = conflicting_skills(facts)
    kept, dropped = [], []
    for keyword in plan['keywords']:
        reason = ('identifier' if has_identifier(keyword) else
                  'excluded_term' if any(contains(keyword, term) for term in excluded) else
                  'conflicting_skill' if any(contains(keyword, skill) for skill in conflicts) else None)
        if reason:
            dropped.append({'reason': reason})  # Do not retain sensitive removed text.
        elif keyword.strip() and normalized(keyword) not in {normalized(k) for k in kept}:
            kept.append(keyword.strip())
    if not kept:
        target = re.split(r'\bor\b|[,;]', preferences.get('target_roles', ''), maxsplit=1, flags=re.I)[0].strip()
        if (not target or len(target) > 100 or has_identifier(target) or COMMAND.search(target)
                or any(contains(target, t) for t in excluded + conflicts)):
            from fastapi import HTTPException
            raise HTTPException(422, 'No usable non-conflicting search terms remain; clarify target roles and profile facts.')
        kept = [target]
    # Controlled rationale avoids repeating identifiers or claiming that a
    # contradictory statement was resolved. Raw model output remains in eval telemetry.
    if conflicts:
        rationale = 'Search uses available role information; conflicting skill statements were left unresolved and omitted.'
    elif not facts:
        rationale = 'Search uses the requested role; no candidate experience was supplied.'
    elif preferences.get('target_roles', '').strip():
        rationale = 'Search uses the requested role and available profile information; excluded terms and identifiers are omitted.'
    else:
        rationale = 'No target role was supplied; search terms use available profile information.'
    result = {'keywords': kept[:6], 'rationale': rationale}
    return result, {'guard_version': VERSION, 'removed_count': len(dropped),
                    'removal_reasons': [d['reason'] for d in dropped], 'conflicting_skill_count': len(conflicts)}
