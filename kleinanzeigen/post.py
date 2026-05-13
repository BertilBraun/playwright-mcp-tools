import tempfile
import urllib.request
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from kleinanzeigen.shared.auth import ensure_logged_in, start_persistent_context

_POST_URL = 'https://www.kleinanzeigen.de/p-anzeige-aufgeben-schritt2.html'

_PRICE_TYPE_LABELS: dict[str, str] = {
    'FIXED': 'Festpreis',
    'NEGOTIABLE': 'Verhandlungsbasis',
    'GIVE_AWAY': 'Zu verschenken',
}

TOOL_DESCRIPTION = {
    'name': 'post_kleinanzeige',
    'description': (
        'Fill in a new Kleinanzeigen listing form. '
        'The browser stays open so you can select the category and submit manually. '
        'Images accept local file paths or https:// URLs. '
        'First-time use: set KLEINANZEIGEN_HEADLESS=false and log in manually — the session is saved.'
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
        'ad_type': {
            'type': 'string',
            'enum': ['OFFER', 'WANTED'],
            'description': 'Offer or wanted listing',
            'default': 'OFFER',
        },
        'zip_code': {'type': 'string', 'description': 'Postal code (PLZ), leave empty to keep profile default'},
        'images': {
            'type': 'array',
            'description': 'Local file paths or https:// URLs (up to 20)',
        },
    },
}

router = APIRouter(prefix='/kleinanzeigen/post', tags=['kleinanzeigen'])

# Keeps playwright + context alive after _run() returns so the browser stays open.
_session: dict = {}


class PostRequest(BaseModel):
    title: str
    description: str
    price_eur: int = 0
    price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'] = 'FIXED'
    ad_type: Literal['OFFER', 'WANTED'] = 'OFFER'
    zip_code: str = ''
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
        request.ad_type,
        request.zip_code,
        request.images,
    )


async def _run(
    title: str,
    description: str,
    price_eur: int,
    price_type: Literal['FIXED', 'NEGOTIABLE', 'GIVE_AWAY'],
    ad_type: Literal['OFFER', 'WANTED'],
    zip_code: str,
    images: list[str],
) -> str:
    await _close_session()

    tmpdir = tempfile.TemporaryDirectory()
    local_images = _resolve_images(images, Path(tmpdir.name))

    playwright, context = await start_persistent_context()
    _session['playwright'] = playwright
    _session['context'] = context
    _session['tmpdir'] = tmpdir

    page = await context.new_page()
    await ensure_logged_in(page)
    await page.goto(_POST_URL, wait_until='domcontentloaded')

    # Ad type radio (sr-only inputs — use JS click to bypass visibility check)
    await page.evaluate(f"document.querySelector('#ad-type-{ad_type}').click()")

    await page.fill('#ad-title', title[:65])
    await page.fill('#ad-description', description[:4000])

    if price_eur > 0:
        await page.fill('#ad-price-amount', str(price_eur))

    if price_type != 'FIXED':
        await _select_price_type(page, price_type)

    if zip_code:
        await page.fill('#ad-zip-code', zip_code)

    if local_images:
        await page.set_input_files('input[type=file][accept*="image"]', [str(p) for p in local_images])
        await page.wait_for_timeout(500)

    note = ' Please select a category before submitting.' if True else ''
    return f'Form filled.{note} Review in the browser and click "Anzeige aufgeben" to submit.'


async def _select_price_type(page, price_type: str) -> None:
    label = _PRICE_TYPE_LABELS[price_type]
    await page.click('#ad-price-type')
    await page.wait_for_timeout(300)
    option = page.get_by_role('option', name=label)
    if await option.count():
        await option.click()


async def _close_session() -> None:
    if not _session:
        return
    try:
        await _session['context'].close()
    except Exception:
        pass
    try:
        await _session['playwright'].stop()
    except Exception:
        pass
    if 'tmpdir' in _session:
        _session['tmpdir'].cleanup()
    _session.clear()


def _resolve_images(images: list[str], tmpdir: Path) -> list[Path]:
    resolved: list[Path] = []
    for index, source in enumerate(images[:20]):
        if source.startswith('https://') or source.startswith('http://'):
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
        ad_type: Literal['OFFER', 'WANTED'] = 'OFFER',
        zip_code: str = '',
        images: list[str] = [],
    ) -> str:
        """Fill in a Kleinanzeigen listing form. Browser stays open for manual category selection and submit. Images accept local paths or https:// URLs."""
        return await _run(title, description, price_eur, price_type, ad_type, zip_code, images)
