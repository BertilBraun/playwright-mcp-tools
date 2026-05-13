import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from playwright.async_api import Page, async_playwright

BASE_URL = 'https://www.dailydose.de'
LOGIN_URL = f'{BASE_URL}/user/anmelden.htm'

T = TypeVar('T')


def _headless() -> bool:
    return os.getenv('DAILYDOSE_HEADLESS', 'true').lower() != 'false'


async def _login(page: Page) -> str:
    email = os.environ['DAILYDOSE_EMAIL']
    password = os.environ['DAILYDOSE_PASSWORD']

    await page.goto(LOGIN_URL, wait_until='domcontentloaded')
    await asyncio.sleep(2)

    await page.fill('input[title="Benutzername oder E-Mail-Adresse eingeben"]', email)
    await page.fill('input[title="Passwort eingeben"]', password)
    await page.click('input[type="submit"], button[type="submit"]')
    await page.wait_for_load_state('domcontentloaded')

    if 'anmelden' in page.url and 'EPsid' not in page.url:
        raise RuntimeError('Login failed – verify DAILYDOSE_EMAIL and DAILYDOSE_PASSWORD')

    m = re.search(r'EPsid=([a-f0-9]+)', page.url)
    if m:
        return m.group(1)

    try:
        href = await page.locator('a[href*="EPsid"]').first.get_attribute('href') or ''
        m = re.search(r'EPsid=([a-f0-9]+)', href)
        if m:
            return m.group(1)
    except Exception:
        pass

    return ''


async def with_logged_in_page(callback: Callable[[Page, str], Awaitable[T]]) -> T:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=_headless(), slow_mo=60)
        context = await browser.new_context(viewport={'width': 1280, 'height': 900})
        page = await context.new_page()
        try:
            epsid = await _login(page)
            return await callback(page, epsid)
        finally:
            await browser.close()
