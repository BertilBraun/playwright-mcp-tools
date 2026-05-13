import os
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright

from kleinanzeigen.shared.log import log

_PROFILE_DIR = Path(os.environ.get('KLEINANZEIGEN_PROFILE_DIR', str(Path.home() / '.kleinanzeigen_profile')))


def start_persistent_context(playwright: Playwright) -> BrowserContext:
    headless = os.environ.get('KLEINANZEIGEN_HEADLESS', 'true').lower() == 'true'
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(_PROFILE_DIR),
        headless=headless,
        viewport={'width': 1280, 'height': 900},
    )


def ensure_logged_in(page: Page, target_url: str) -> None:
    log(f'[auth] Navigating to {target_url}...')
    page.goto(target_url, wait_until='load')
    page.wait_for_timeout(2000)

    if not page.locator('input[name="username"]').count():
        log('[auth] Already logged in, skipping login.')
        return

    log('[auth] Login form detected, starting login flow...')
    email = os.environ['KLEINANZEIGEN_EMAIL']
    password = os.environ['KLEINANZEIGEN_PASSWORD']

    log('[auth] Filling email...')
    page.fill('input[name="username"]', email)
    page.wait_for_timeout(500)
    page.click('button._button-login-id')
    log('[auth] Clicked "Weiter", waiting for password field...')
    page.wait_for_selector('input[name="password"]', state='visible', timeout=60000)
    page.wait_for_timeout(2000)

    log('[auth] Filling password...')
    page.fill('input[name="password"]', password)
    page.wait_for_timeout(500)
    page.click('button._button-login-password')
    log('[auth] Clicked "Einloggen", waiting for login to complete...')
    page.wait_for_selector('input[name="username"]', state='hidden', timeout=60000)
    page.wait_for_timeout(2000)
    log('[auth] Login complete.')
