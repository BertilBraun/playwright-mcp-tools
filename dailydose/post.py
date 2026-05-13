import asyncio
import re
import tempfile
import urllib.request
from pathlib import Path

from fastapi import APIRouter
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from dailydose.shared.auth import with_logged_in_page

BASE_URL = 'https://www.dailydose.de'
UPLOAD_URL = f'{BASE_URL}/kleinanzeigen/upload.htm'

TOOL_DESCRIPTION = {
    'name': 'post_listing',
    'description': (
        'Post a new listing on DailyDose.de. '
        'Images accept local file paths or https:// URLs (max 10). '
        'Returns the new listing ID. '
        'Requires DAILYDOSE_EMAIL and DAILYDOSE_PASSWORD.'
    ),
    'parameters': {
        'title': {'type': 'string', 'description': 'Listing title'},
        'description': {'type': 'string', 'description': 'Listing description text'},
        'price': {'type': 'string', 'description': "Price as text, e.g. '450' or '450 VB'"},
        'zip_code': {'type': 'string', 'description': 'Postal code (PLZ)'},
        'location': {'type': 'string', 'description': 'City or location name'},
        'category_id': {
            'type': 'string',
            'description': "Numeric category ID from the 'kategorie' select on the upload form",
        },
        'images': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Local file paths or https:// URLs (max 10)',
        },
    },
}

router = APIRouter(prefix='/dailydose/post', tags=['dailydose'])


class PostRequest(BaseModel):
    title: str
    description: str
    price: str
    zip_code: str
    location: str
    category_id: str
    images: list[str] = []


@router.get('/')
def describe() -> dict:
    return TOOL_DESCRIPTION


@router.post('/')
async def run(request: PostRequest) -> str:
    return await _run(
        request.title,
        request.description,
        request.price,
        request.zip_code,
        request.location,
        request.category_id,
        request.images,
    )


async def _run(
    title: str,
    description: str,
    price: str,
    zip_code: str,
    location: str,
    category_id: str,
    images: list[str],
) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        local_images = _resolve_images(images, Path(tmpdir))

        async def do_post(page, epsid: str) -> str:
            await page.goto(f'{UPLOAD_URL}?EPsid={epsid}', wait_until='domcontentloaded')
            await asyncio.sleep(2)

            await page.fill('input[name="titel"]', title)
            await page.fill('textarea[name="text"]', description)
            await page.fill('input[name="preis"]', price)
            await page.fill('input[name="plz"]', zip_code)
            await page.fill('input[name="ort"]', location)

            if category_id:
                await page.select_option('select[name="kategorie"]', value=category_id)

            for index, img_path in enumerate(local_images[:10], start=1):
                file_input = page.locator(f'input[name="image{index}"]').first
                if await file_input.count():
                    await file_input.set_input_files(str(img_path))
                    await page.wait_for_timeout(200)

            await page.click('input[type="submit"][value*="eintragen"]')
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(1500)

            new_url = page.url
            id_match = re.search(r'ai=(\d+)', new_url)
            return id_match.group(1) if id_match else new_url

        return await with_logged_in_page(do_post)


def _resolve_images(images: list[str], tmpdir: Path) -> list[Path]:
    resolved: list[Path] = []
    for index, source in enumerate(images[:10]):
        if source.startswith('http://') or source.startswith('https://'):
            extension = Path(source.split('?')[0]).suffix.lower() or '.jpg'
            destination = tmpdir / f'image_{index:02d}{extension}'
            urllib.request.urlretrieve(source, destination)
            resolved.append(destination)
        else:
            resolved.append(Path(source))
    return resolved


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def post_listing(
        title: str,
        description: str,
        price: str,
        zip_code: str,
        location: str,
        category_id: str,
        images: list[str],
    ) -> str:
        """Post a new DailyDose.de listing. images accepts local file paths or https:// URLs. Returns the new listing ID. Requires DAILYDOSE_EMAIL and DAILYDOSE_PASSWORD."""
        return await _run(title, description, price, zip_code, location, category_id, images)
