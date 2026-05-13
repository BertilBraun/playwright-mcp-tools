import os
from pathlib import Path

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

_PROFILE_DIR = Path(os.environ.get('KLEINANZEIGEN_PROFILE_DIR', str(Path.home() / '.kleinanzeigen_profile')))
_HOME_URL = 'https://www.kleinanzeigen.de'
_LOGIN_URL = 'https://www.kleinanzeigen.de/m-einloggen.html'


async def start_persistent_context() -> tuple[Playwright, BrowserContext]:
    headless = os.environ.get('KLEINANZEIGEN_HEADLESS', 'true').lower() == 'true'
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    playwright = await async_playwright().start()
    context = await playwright.chromium.launch_persistent_context(
        str(_PROFILE_DIR),
        headless=headless,
        viewport={'width': 1280, 'height': 900},
    )
    return playwright, context


async def ensure_logged_in(page: Page) -> None:
    """Navigate to the home page and log in if needed. Credentials from env vars."""
    await page.goto(_HOME_URL, wait_until='domcontentloaded')

    login_btn = page.get_by_test_id('login-button')
    if not await login_btn.count():
        return  # already logged in

    email = os.environ['KLEINANZEIGEN_EMAIL']
    password = os.environ['KLEINANZEIGEN_PASSWORD']

    await login_btn.click()
    await page.wait_for_url(f'{_LOGIN_URL}**', wait_until='domcontentloaded')

    await page.fill('input[name="username"]', email)
    await page.click('button._button-login-id')
    await page.wait_for_selector('input[name="password"]')

    await page.fill('input[name="password"]', password)
    await page.click('button._button-login-password')
    await page.wait_for_url(f'{_HOME_URL}**', wait_until='domcontentloaded')
