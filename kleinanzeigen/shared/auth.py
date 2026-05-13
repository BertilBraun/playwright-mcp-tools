import os
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright

_PROFILE_DIR = Path(os.environ.get('KLEINANZEIGEN_PROFILE_DIR', str(Path.home() / '.kleinanzeigen_profile')))
_HOME_URL = 'https://www.kleinanzeigen.de'


def start_persistent_context(playwright: Playwright) -> BrowserContext:
    headless = os.environ.get('KLEINANZEIGEN_HEADLESS', 'true').lower() == 'true'
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(_PROFILE_DIR),
        headless=headless,
        viewport={'width': 1280, 'height': 900},
    )


def ensure_logged_in(page: Page) -> None:
    print('[auth] Navigating to home page...')
    page.goto(_HOME_URL, wait_until='load')
    page.wait_for_timeout(2000)

    if not page.locator('[data-testid="login-button"]').count():
        print('[auth] Already logged in, skipping login.')
        return

    print('[auth] Login button found, starting login flow...')
    email = os.environ['KLEINANZEIGEN_EMAIL']
    password = os.environ['KLEINANZEIGEN_PASSWORD']

    page.locator('[data-testid="login-button"]').click()
    print('[auth] Clicked login button, waiting for email field...')
    page.wait_for_selector('input[name="username"]', state='visible', timeout=60000)
    page.wait_for_timeout(2000)

    print('[auth] Filling email...')
    page.fill('input[name="username"]', email)
    page.wait_for_timeout(500)
    page.click('button._button-login-id')
    print('[auth] Clicked "Weiter", waiting for password field...')
    page.wait_for_selector('input[name="password"]', state='visible', timeout=60000)
    page.wait_for_timeout(2000)

    print('[auth] Filling password...')
    page.fill('input[name="password"]', password)
    page.wait_for_timeout(500)
    page.click('button._button-login-password')
    print('[auth] Clicked "Einloggen", waiting for login button to disappear...')
    page.wait_for_selector('[data-testid="login-button"]', state='hidden', timeout=60000)
    page.wait_for_timeout(2000)
    print('[auth] Login complete.')
