import asyncio
import base64
import multiprocessing
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

_POST_URL = 'https://www.kleinanzeigen.de/p-anzeige-aufgeben-schritt2.html'

_PRICE_TYPE_LABELS: dict[str, str] = {
    'FIXED': 'Festpreis',
    'NEGOTIABLE': 'Verhandlungsbasis',
    'GIVE_AWAY': 'Zu verschenken',
}

TOOL_DESCRIPTION = {
    'name': 'post_kleinanzeige',
    'endpoint': '/kleinanzeigen/post/',
    'description': (
        'Fill in a new Kleinanzeigen listing form. '
        'The browser stays open so you can select the category and submit manually. '
        'First-time use: set KLEINANZEIGEN_HEADLESS=false to log in — the session is then saved.'
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
        'images': {
            'type': 'files',
            'description': 'Photos for the listing (up to 20)',
        },
    },
}

router = APIRouter(prefix='/kleinanzeigen/post', tags=['kleinanzeigen'])

_active_process: multiprocessing.Process | None = None


class PostRequest(BaseModel):
    title: str
    description: str
    price_eur: int = 0
    price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'] = 'FIXED'
    images: list[str] = []


@router.get('/')
def describe() -> dict:
    return TOOL_DESCRIPTION


@router.post('/')
async def run(request: PostRequest) -> str:
    return await _run(
        request.title,
        request.description,
        request.price_eur,
        request.price_type,
        request.images,
    )


async def _run(
    title: str,
    description: str,
    price_eur: int,
    price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'],
    images: list[str],
) -> str:
    global _active_process
    if _active_process and _active_process.is_alive():
        _active_process.terminate()
        _active_process.join()

    queue: multiprocessing.Queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_worker,
        args=(queue, title, description, price_eur, price_type, images),
        daemon=True,
    )
    process.start()
    _active_process = process

    return await asyncio.to_thread(queue.get)


def _worker(
    queue: multiprocessing.Queue,
    title: str,
    description: str,
    price_eur: int,
    price_type: str,
    images: list[str],
) -> None:
    from playwright.sync_api import sync_playwright

    from kleinanzeigen.shared.auth import ensure_logged_in, start_persistent_context

    with tempfile.TemporaryDirectory() as tmpdir:
        local_images = _resolve_images(images, Path(tmpdir))
        try:
            with sync_playwright() as playwright:
                print('[post] Launching browser...')
                context = start_persistent_context(playwright)
                page = context.new_page()
                ensure_logged_in(page)

                print(f'[post] Navigating to listing form: {_POST_URL}')
                page.goto(_POST_URL, wait_until='load')

                print('[post] Setting ad type to OFFER...')
                page.evaluate("document.querySelector('#ad-type-OFFER').click()")

                print(f'[post] Filling title: {title[:65]!r}')
                page.fill('#ad-title', title[:65])

                print(f'[post] Filling description ({len(description)} chars)...')
                page.fill('#ad-description', description[:4000])

                if price_eur > 0:
                    print(f'[post] Filling price: {price_eur}')
                    page.fill('#ad-price-amount', str(price_eur))

                if price_type != 'FIXED':
                    label = _PRICE_TYPE_LABELS[price_type]
                    print('[post] Opening price type dropdown...')
                    page.click('#ad-price-type')
                    print('[post] Waiting for listbox to appear...')
                    page.wait_for_selector('[role="listbox"]', state='visible', timeout=10000)
                    page.wait_for_timeout(500)
                    print(f'[post] Looking for option "{label}"...')
                    option = page.locator(f'[role="option"]:has-text("{label}")')
                    if option.count():
                        print(f'[post] Clicking option "{label}"...')
                        option.first.click()
                        page.wait_for_selector('[role="listbox"]', state='hidden', timeout=5000)
                        print(f'[post] Price type set to "{label}".')
                    else:
                        print(f'[post] Warning: option "{label}" not found, closing dropdown')
                        page.keyboard.press('Escape')

                if local_images:
                    paths = [str(p) for p in local_images]
                    print(f'[post] Uploading {len(paths)} image(s): {paths}')
                    page.set_input_files('input[type=file][accept*="image"]', paths)
                    print('[post] Waiting for images to process...')
                    page.wait_for_timeout(2000)

                print('[post] Form filled. Waiting for browser to close...')
                queue.put('Form filled. Please select a category, then click "Anzeige aufgeben" to submit.')
                page.wait_for_event('close', timeout=0)
                print('[post] Browser closed.')
        except Exception as exc:
            print(f'[post] Error: {exc}')
            queue.put(f'Error: {exc}')


def _resolve_images(images: list[str], tmpdir: Path) -> list[Path]:
    resolved: list[Path] = []
    for index, source in enumerate(images[:20]):
        if source.startswith('data:'):
            match = re.match(r'data:image/(\w+);base64,(.+)', source, re.DOTALL)
            if match:
                ext, data = match.group(1), match.group(2)
                destination = tmpdir / f'image_{index:02d}.{ext}'
                destination.write_bytes(base64.b64decode(data))
                resolved.append(destination)
        elif source.startswith('https://') or source.startswith('http://'):
            extension = Path(source.split('?')[0]).suffix.lower() or '.jpg'
            destination = tmpdir / f'image_{index:02d}{extension}'
            urllib.request.urlretrieve(source, destination)
            resolved.append(destination)
        else:
            resolved.append(Path(source))
    return resolved


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def post_kleinanzeige(
        title: str,
        description: str,
        price_eur: int = 0,
        price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'] = 'FIXED',
        images: list[str] = [],
    ) -> str:
        """Fill in a Kleinanzeigen listing form. Browser stays open for manual category selection and submit."""
        return await _run(title, description, price_eur, price_type, images)
