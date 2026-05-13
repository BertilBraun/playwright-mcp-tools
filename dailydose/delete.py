import asyncio

from fastapi import APIRouter
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from dailydose.shared.auth import with_logged_in_page

BASE_URL = 'https://www.dailydose.de'
MANAGE_URL = f'{BASE_URL}/kleinanzeigen/anmelden.htm'

TOOL_DESCRIPTION = {
    'name': 'delete_listing',
    'description': 'Delete a DailyDose.de listing by ID. Requires DAILYDOSE_EMAIL and DAILYDOSE_PASSWORD.',
    'parameters': {
        'listing_id': {
            'type': 'string',
            'description': 'Numeric listing ID to delete',
        },
    },
}

router = APIRouter(prefix='/dailydose/delete', tags=['dailydose'])


class DeleteRequest(BaseModel):
    listing_id: str


@router.get('/')
def describe() -> dict:
    return TOOL_DESCRIPTION


@router.post('/')
async def run(request: DeleteRequest) -> bool:
    return await _run(request.listing_id)


async def _run(listing_id: str) -> bool:
    async def do_delete(page, epsid: str) -> bool:
        await page.goto(f'{MANAGE_URL}?EPsid={epsid}', wait_until='domcontentloaded')
        await asyncio.sleep(2)

        delete_link = page.locator(f'a[href*="id={listing_id}"][title*="löschen"]').first
        if not await delete_link.count():
            delete_link = page.locator(f'a[href*="loeschen"][href*="id={listing_id}"]').first
        if not await delete_link.count():
            delete_link = page.locator(f'a[href*="id={listing_id}"] span.red').first
        if not await delete_link.count():
            raise RuntimeError(f'Delete link for listing {listing_id} not found on management page.')

        page.once('dialog', lambda dialog: asyncio.ensure_future(dialog.accept()))
        await delete_link.click()
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(800)
        return True

    return await with_logged_in_page(do_delete)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def delete_listing(listing_id: str) -> bool:
        """Delete a DailyDose.de listing by ID. Requires DAILYDOSE_EMAIL and DAILYDOSE_PASSWORD environment variables."""
        return await _run(listing_id)
