import asyncio
import threading
from typing import Literal

from fastapi import APIRouter
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from kleinanzeigen.shared.log import log

_POST_URL = 'https://www.kleinanzeigen.de/p-anzeige-aufgeben-schritt2.html'

_PRICE_TYPE_LABELS: dict[str, str] = {
    'FIXED': 'Festpreis',
    'NEGOTIABLE': 'VB',
    'GIVE_AWAY': 'Zu verschenken',
}

TOOL_DESCRIPTION = {
    'name': 'post_kleinanzeige',
    'endpoint': '/kleinanzeigen/post/',
    'description': (
        'Fill in a new Kleinanzeigen listing form. '
        'The browser stays open for review before submitting. '
        'Requires KLEINANZEIGEN_EMAIL and KLEINANZEIGEN_PASSWORD.'
    ),
    'parameters': {
        'title': {'type': 'string', 'description': 'Listing title (max 65 characters)'},
        'description': {'type': 'string', 'description': 'Listing description (max 4000 characters)'},
        'price_eur': {'type': 'integer', 'description': 'Price in euros (0 = omit price field)', 'default': 0},
        'price_type': {
            'type': 'string',
            'enum': ['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'],
            'description': 'Price type',
            'default': 'FIXED',
        },
    },
}

router = APIRouter(prefix='/kleinanzeigen/post', tags=['kleinanzeigen'])

# Kept at module level so the browser stays open after _run_sync returns.
_active_context = None
_active_context_lock = threading.Lock()


class PostRequest(BaseModel):
    title: str
    description: str
    price_eur: int = 0
    price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'] = 'FIXED'


@router.get('/')
def describe() -> dict[str, object]:
    return TOOL_DESCRIPTION


@router.post('/')
async def run(request: PostRequest) -> str:
    return await _run(
        request.title,
        request.description,
        request.price_eur,
        request.price_type,
    )


async def _run(
    title: str,
    description: str,
    price_eur: int,
    price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'],
) -> str:
    return await asyncio.to_thread(_run_sync, title, description, price_eur, price_type)


def _run_sync(
    title: str,
    description: str,
    price_eur: int,
    price_type: str,
) -> str:
    global _active_context

    from playwright.sync_api import sync_playwright

    from kleinanzeigen.shared.auth import ensure_logged_in, start_persistent_context

    with _active_context_lock:
        if _active_context is not None:
            try:
                _active_context.close()
            except Exception:
                pass

    try:
        if len(title) > 65:
            raise ValueError(f'Title too long: {len(title)} characters (max 65)')
        if len(description) > 4000:
            raise ValueError(f'Description too long: {len(description)} characters (max 4000)')

        with sync_playwright() as playwright:
            log('[post] Launching browser...')
            context = start_persistent_context(playwright)
            with _active_context_lock:
                _active_context = context

            page = context.new_page()
            ensure_logged_in(page, _POST_URL)

            log('[post] Setting ad type to OFFER...')
            page.evaluate("document.querySelector('#ad-type-OFFER').click()")
            page.wait_for_timeout(1000)

            log(f'[post] Filling title: {title!r}')
            page.fill('#ad-title', title)
            page.wait_for_timeout(2000)

            log(f'[post] Filling description ({len(description)} chars)...')
            page.fill('#ad-description', description)
            page.wait_for_timeout(1000)

            if price_eur > 0:
                log(f'[post] Filling price: {price_eur}')
                page.fill('#ad-price-amount', str(price_eur))
                page.wait_for_timeout(1000)

            if price_type != 'FIXED':
                label = _PRICE_TYPE_LABELS[price_type]
                log('[post] Opening price type dropdown...')
                page.click('#ad-price-type')
                page.wait_for_selector('[role="listbox"]', state='visible', timeout=10000)
                page.wait_for_timeout(500)
                option = page.locator(f'[role="option"]:has-text("{label}")')
                if option.count():
                    log(f'[post] Clicking option "{label}"...')
                    option.first.click()
                    page.wait_for_selector('[role="listbox"]', state='hidden', timeout=5000)
                    log(f'[post] Price type set to "{label}".')
                else:
                    page.keyboard.press('Escape')
                    raise ValueError(f'Price type option "{label}" not found in dropdown')

            log('[post] Waiting for category suggestions...')
            try:
                page.wait_for_selector('#ad-category-picker input[type="radio"]', state='visible', timeout=10000)
                page.wait_for_timeout(1000)
                first_radio_id = page.locator('#ad-category-picker input[type="radio"]').first.get_attribute('id')
                label_text = page.locator(f'label[for="{first_radio_id}"]').inner_text()
                log(f'[post] Selecting first suggested category: {label_text!r}')
                page.evaluate('document.querySelector(\'#ad-category-picker input[type="radio"]\').click()')
                page.wait_for_timeout(1000)
            except Exception:
                log('[post] No category suggestions found, leaving for manual selection.')

            log('[post] Form filled. Waiting for browser to close...')
            page.wait_for_event('close', timeout=0)
            log('[post] Browser closed.')
            return 'Form filled without images. Review in the browser, add photos manually, and click "Anzeige aufgeben" to submit.'

    except Exception as exc:
        log(f'[post] Error: {exc}')
        return f'Error: {exc}'


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def post_kleinanzeige(
        title: str,
        description: str,
        price_eur: int = 0,
        price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'] = 'FIXED',
    ) -> str:
        """Fill in Kleinanzeigen listing text fields. Add photos manually before submitting."""
        return await _run(title, description, price_eur, price_type)
