import base64
import re
import tempfile
import threading
import urllib.request
from pathlib import Path
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
        'images': {
            'type': 'files',
            'description': 'Photos for the listing (up to 20)',
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
    images: list[str] = []


@router.get('/')
def describe() -> dict:
    return TOOL_DESCRIPTION


@router.post('/')
async def run(request: PostRequest) -> str:
    return _run(
        request.title,
        request.description,
        request.price_eur,
        request.price_type,
        request.images,
    )


def _run(
    title: str,
    description: str,
    price_eur: int,
    price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'],
    images: list[str],
) -> str:
    return _run_sync(title, description, price_eur, price_type, images)


def _run_sync(
    title: str,
    description: str,
    price_eur: int,
    price_type: str,
    images: list[str],
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

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            if len(title) > 65:
                raise ValueError(f'Title too long: {len(title)} characters (max 65)')
            if len(description) > 4000:
                raise ValueError(f'Description too long: {len(description)} characters (max 4000)')

            local_images = _resolve_images(images, Path(tmpdir))

            with sync_playwright() as playwright:
                log('[post] Launching browser...')
                context = start_persistent_context(playwright)
                with _active_context_lock:
                    _active_context = context

                page = context.new_page()
                ensure_logged_in(page)

                log(f'[post] Navigating to listing form: {_POST_URL}')
                page.goto(_POST_URL, wait_until='load')

                log('[post] Setting ad type to OFFER...')
                page.evaluate("document.querySelector('#ad-type-OFFER').click()")

                log(f'[post] Filling title: {title!r}')
                page.fill('#ad-title', title)
                page.wait_for_timeout(1000)

                log(f'[post] Filling description ({len(description)} chars)...')
                page.fill('#ad-description', description)

                log('[post] Waiting for category suggestions...')
                page.wait_for_selector('#ad-category-picker input[type="radio"]', state='visible', timeout=8000)
                page.wait_for_timeout(500)
                first_radio_id = page.locator('#ad-category-picker input[type="radio"]').first.get_attribute('id')
                label_text = page.locator(f'label[for="{first_radio_id}"]').inner_text()
                log(f'[post] Selecting first suggested category: {label_text!r}')
                page.evaluate('document.querySelector(\'#ad-category-picker input[type="radio"]\').click()')
                page.wait_for_timeout(500)

                if price_eur > 0:
                    log(f'[post] Filling price: {price_eur}')
                    page.fill('#ad-price-amount', str(price_eur))

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

                if local_images:
                    paths = [str(p) for p in local_images]
                    log(f'[post] Uploading {len(paths)} image(s): {paths}')
                    page.set_input_files('input[type=file][accept*="image"]', paths)
                    page.wait_for_timeout(2000)

                log('[post] Form filled. Waiting for browser to close...')
                page.wait_for_event('close', timeout=0)
                log('[post] Browser closed.')
                return 'Form filled. Review in the browser and click "Anzeige aufgeben" to submit.'

        except Exception as exc:
            log(f'[post] Error: {exc}')
            return f'Error: {exc}'


_MAX_IMAGE_BYTES = 12 * 1024 * 1024


def _resolve_images(images: list[str], tmpdir: Path) -> list[Path]:
    resolved: list[Path] = []
    for index, source in enumerate(images[:20]):
        if source.startswith('data:'):
            match = re.match(r'data:image/(\w+);base64,(.+)', source, re.DOTALL)
            if match:
                ext, data = match.group(1), match.group(2)
                destination = tmpdir / f'image_{index:02d}.{ext}'
                destination.write_bytes(base64.b64decode(data))
                resolved.append(_compress_if_needed(destination, tmpdir, index))
        elif source.startswith('https://') or source.startswith('http://'):
            extension = Path(source.split('?')[0]).suffix.lower() or '.jpg'
            destination = tmpdir / f'image_{index:02d}{extension}'
            urllib.request.urlretrieve(source, destination)
            resolved.append(_compress_if_needed(destination, tmpdir, index))
        else:
            resolved.append(_compress_if_needed(Path(source), tmpdir, index))
    return resolved


def _compress_if_needed(path: Path, tmpdir: Path, index: int) -> Path:
    size_mb = path.stat().st_size / 1024 / 1024
    if path.stat().st_size <= _MAX_IMAGE_BYTES:
        return path

    from PIL import Image

    log(f'[post] Image {path.name} is {size_mb:.1f} MB, compressing...')
    img = Image.open(path).convert('RGB')
    output = tmpdir / f'image_{index:02d}_compressed.jpg'
    for quality in range(85, 10, -10):
        img.save(output, 'JPEG', quality=quality)
        if output.stat().st_size <= _MAX_IMAGE_BYTES:
            log(f'[post] Compressed to {output.stat().st_size / 1024 / 1024:.1f} MB (quality={quality})')
            return output

    raise ValueError(f'{path.name} cannot be compressed below 12 MB')


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def post_kleinanzeige(
        title: str,
        description: str,
        price_eur: int = 0,
        price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'] = 'FIXED',
        images: list[str] = [],
    ) -> str:
        """Fill in a Kleinanzeigen listing form. Browser stays open for review before submitting."""
        return _run(title, description, price_eur, price_type, images)
