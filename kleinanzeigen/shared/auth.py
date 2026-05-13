import os
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright

_PROFILE_DIR = Path(os.environ.get('KLEINANZEIGEN_PROFILE_DIR', str(Path.home() / '.kleinanzeigen_profile')))
_HOME_URL = 'https://www.kleinanzeigen.de'
_LOGIN_URL = 'https://www.kleinanzeigen.de/m-einloggen.html'


def start_persistent_context(playwright: Playwright) -> BrowserContext:
    headless = os.environ.get('KLEINANZEIGEN_HEADLESS', 'true').lower() == 'true'
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(_PROFILE_DIR),
        headless=headless,
        viewport={'width': 1280, 'height': 900},
    )


def ensure_logged_in(page: Page) -> None:
    page.goto(_HOME_URL, wait_until='networkidle')
    page.wait_for_timeout(2000)

    if not page.locator('[data-testid="login-button"]').count():
        return

    email = os.environ['KLEINANZEIGEN_EMAIL']
    password = os.environ['KLEINANZEIGEN_PASSWORD']

    page.locator('[data-testid="login-button"]').click()
    page.wait_for_url(f'{_LOGIN_URL}**', wait_until='networkidle')
    page.wait_for_timeout(2000)

    page.fill('input[name="username"]', email)
    page.wait_for_timeout(500)
    page.click('button._button-login-id')
    page.wait_for_selector('input[name="password"]', state='visible')
    page.wait_for_timeout(2000)

    page.fill('input[name="password"]', password)
    page.wait_for_timeout(500)
    page.click('button._button-login-password')
    page.wait_for_url(f'{_HOME_URL}**', wait_until='networkidle')
    page.wait_for_timeout(2000)
