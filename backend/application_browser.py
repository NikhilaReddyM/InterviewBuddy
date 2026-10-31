"""Dedicated local browser process. Fills fields, optionally saves drafts; NEVER submits."""
import argparse
from contextlib import contextmanager
import fcntl
import re
from urllib.parse import urlsplit, parse_qs

from application_forms import read, save, fetch_schema, fields_from_schema, field_signature, attachment_path
from workspaces import now


@contextmanager
def browser_lock(store, workspace_id):
    folder = store.root / 'application-browsers'
    folder.mkdir(exist_ok=True, mode=0o700)
    with (folder / f'{workspace_id}.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def browser_available(store, workspace_id):
    with browser_lock(store, workspace_id) as available:
        return available


def trusted_url(url):
    try:
        parsed = urlsplit(url)
        return parsed.scheme == 'https' and parsed.hostname in ('job-boards.greenhouse.io', 'boards.greenhouse.io') and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except ValueError:
        return False


def matches_application(url, plan):
    if not trusted_url(url):
        return False
    parsed = urlsplit(url)
    if url == plan.get('remote_draft_url'):
        return True
    query = parse_qs(parsed.query)
    return bool(re.fullmatch(r'/' + re.escape(plan['board']) + r'/jobs/' + re.escape(plan['job_id']) + r'/?', parsed.path)
                or (parsed.path == '/embed/job_app' and query.get('for') == [plan['board']] and query.get('token') == [plan['job_id']]))


def application_frame(page, plan, employer_url):
    # Employers such as MongoDB redirect the public listing to a branded page.
    # Fill only the exact job's Greenhouse iframe, never arbitrary employer DOM.
    root = urlsplit(page.url)
    employer = urlsplit(employer_url)
    if not trusted_url(page.url) and not (root.scheme == 'https' and root.hostname == employer.hostname and not root.username):
        return None
    for _ in range(60):
        frames = [frame for frame in page.frames if matches_application(frame.url, plan)]
        if len(frames) == 1 and frames[0].locator('input[id=first_name], input[name=first_name], input[type=file]').count():
            return frames[0]
        page.wait_for_timeout(500)
    return None


def field_locator(page, field):
    direct = page.locator(f'[id="{field["name"]}"], [name="{field["name"]}"]')
    if direct.count() == 1:
        return direct
    if field['name'] in ('cover_letter_text', 'resume_text') and direct.count() == 0:
        # Greenhouse initially hides plain-text alternatives behind Enter manually.
        file_input = page.locator(f'input[id="{field["name"][:-5]}"]')
        container = page.locator('.file-upload').filter(has=file_input)
        if container.count() == 1:
            toggle = container.get_by_role('button', name='Enter manually', exact=True)
            if toggle.count() == 1:
                toggle.click(timeout=5000)
                if direct.count() == 1:
                    return direct
    label = re.compile(r'^' + re.escape(field['label'].rstrip(' *')) + r'\s*\*?$', re.I)
    found = page.get_by_label(label)
    return found if found.count() == 1 else None


def fill_fields(page, plan, resume_path):
    results = []
    for field in plan['fields']:
        if field.get('value') is None:
            continue
        result = {'name': field['name'], 'label': field['label'], 'status': 'not_filled'}
        try:
            locator = field_locator(page, field)
            if locator is None:
                result['reason'] = 'Could not uniquely identify this field. Complete it in the browser.'
            elif field['type'] == 'input_file':
                if field['name'] == 'resume' and resume_path:
                    locator.set_input_files(str(resume_path), timeout=5000)
                    result['status'] = 'filled'
                else:
                    result['reason'] = 'Attachment requires manual selection.'
            elif field['type'] == 'multi_value_single_select':
                label = next(c['label'] for c in field['choices'] if c['value'] == field['value'])
                tag = locator.evaluate('(el) => el.tagName.toLowerCase()')
                if tag == 'select':
                    locator.select_option(label=label, timeout=5000)
                else:
                    # React Select: click only the identified control and exact option.
                    locator.click(timeout=5000)
                    option = page.get_by_role('option', name=label, exact=True)
                    if option.count() != 1:
                        raise ValueError('Ambiguous option')
                    option.click(timeout=5000)
                result['status'] = 'filled'
            elif field['type'] in ('input_text', 'textarea'):
                # Never interact with hidden/password/submit controls, even if a site
                # changes its markup to reuse a previously known field ID.
                input_type = locator.get_attribute('type') or 'text'
                if input_type in ('hidden', 'password', 'submit', 'button', 'checkbox', 'radio'):
                    raise ValueError('Unsupported control')
                locator.fill(field['value'], timeout=5000)
                result['status'] = 'filled'
            else:
                result['reason'] = 'This control needs manual completion.'
        except Exception:
            result['reason'] = 'This field could not be filled automatically; review it in the browser.'
        results.append(result)
    return results


def try_save_draft(page):
    # A narrowly named save action is allowed; Submit/Apply/Continue are never
    # clicked. Mark a remote draft only after explicit confirmation plus resume URL.
    button = page.get_by_role('button', name=re.compile(r'^save (?:draft|application draft|and finish later)$', re.I))
    if button.count() != 1 or not button.is_visible():
        return None
    button.click(timeout=5000)
    saved = page.get_by_text(re.compile(r'^(?:application )?draft saved[.!]?$', re.I))
    saved.first.wait_for(state='visible', timeout=5000)
    link = page.get_by_role('link', name=re.compile(r'^(?:resume|continue) (?:your )?application$', re.I))
    if link.count() == 1:
        from urllib.parse import urljoin
        url = urljoin(page.url, link.get_attribute('href') or '')
        if trusted_url(url):
            return url
    return None


def update_status(store, workspace_id, **changes):
    # Do not overwrite answers edited while a browser is open.
    current = read(store, workspace_id)
    return save(store, workspace_id, {**current, **changes}, current['revision'])


def run(store, workspace_id, review):
    with browser_lock(store, workspace_id) as acquired:
        if not acquired:
            return
        plan = read(store, workspace_id)
        try:
            if not trusted_url(plan.get('application_url', '')):
                raise ValueError('Unsupported URL')
            # Recheck actual field schema before uploading any candidate information.
            schema = fetch_schema(plan['board'], plan['job_id'])
            current = fields_from_schema(schema)
            if [field_signature(f) for f in current] != [field_signature(f) for f in plan['fields']]:
                update_status(store, workspace_id, status='attention', schema_changed=True,
                              message='The employer changed this form. Refresh application fields before restoring answers.')
                return
            from playwright.sync_api import sync_playwright
            update_status(store, workspace_id, status='opening', message='Opening the employer application and restoring saved answers. Nothing is submitted.')
            with sync_playwright() as playwright:
                profile = store.root / 'application-browsers' / workspace_id
                profile.mkdir(exist_ok=True, mode=0o700)
                context = playwright.chromium.launch_persistent_context(str(profile), headless=not review, accept_downloads=False)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    # Only navigate/fill supported Greenhouse pages. Redirects to
                    # login or another service stop automatic interaction.
                    employer_url = schema.get('absolute_url') or plan['application_url']
                    parsed_employer = urlsplit(employer_url)
                    destination = employer_url if parsed_employer.scheme == 'https' and not parsed_employer.username else plan['application_url']
                    page.goto(plan.get('remote_draft_url') or destination, wait_until='domcontentloaded', timeout=45000)
                    form = application_frame(page, plan, employer_url)
                    if form is None:
                        update_status(store, workspace_id, status='attention', message='Could not locate this job’s supported Greenhouse form. Check the browser for login or verification, or open the original link manually.')
                        return
                    form.locator('input:not([type=hidden]), textarea, select').first.wait_for(timeout=20000)
                    results = fill_fields(form, plan, attachment_path(store, plan.get('attachment')))
                    remote_url = None
                    try:
                        remote_url = try_save_draft(form)
                    except Exception:
                        pass  # Local SQLite plan remains authoritative if save fails.
                    incomplete = bool(plan.get('missing_required')) or any(r['status'] != 'filled' for r in results)
                    update_status(store, workspace_id,
                                  status='saved_on_site' if remote_url else 'browser_ready' if review else 'needs_answers' if incomplete else 'local_draft',
                                  remote_draft_url=remote_url, handoff='saved_on_site' if remote_url else 'restore_in_browser',
                                  browser_results=results, last_prepared_at=now(),
                                  message='Employer draft saved; use Review application to reopen it.' if remote_url else
                                  'Application is open in the dedicated browser. Review all fields and submit there yourself.' if review else
                                  'Browser preparation finished. Answers are saved locally and will be restored when you choose Review application. No employer-side saved draft was confirmed.')
                    if review:
                        page.bring_to_front()
                        # Hand control to the human. No further automation runs in
                        # this window, including after they press Submit themselves.
                        while context.pages:
                            try:
                                page.wait_for_timeout(1000)
                            except Exception:
                                break
                finally:
                    context.close()
                if review:
                    current = read(store, workspace_id)
                    if current['status'] == 'browser_ready':
                        update_status(store, workspace_id, status='local_draft', message='Browser session closed. Saved answers remain available; choose Review application to restore them again.')
        except Exception as error:
            from fastapi import HTTPException
            message = error.detail if isinstance(error, HTTPException) else 'Browser preparation stopped. Your answers are saved. Check login/CAPTCHA, browser installation, or changed form fields, then reopen the application.'
            update_status(store, workspace_id, status='attention', message=message)


def main():
    from pathlib import Path
    from workspaces import Store
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--mode', choices=['prepare', 'review'], default='review')
    args = parser.parse_args()
    store = Store(args.data_dir)
    # Resolve a real stored ID before using it in a profile/lock path.
    store.detail(args.workspace)
    if not re.fullmatch(r'[a-f0-9-]{36}', args.workspace):
        raise SystemExit('Invalid workspace ID')
    run(store, args.workspace, args.mode == 'review')


if __name__ == '__main__':
    main()
