import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from fastapi import APIRouter
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from dailydose.shared.http_session import make_session

BASE_URL = 'https://www.dailydose.de'

TOOL_DESCRIPTION = {
    'name': 'fetch_listing',
    'description': 'Fetch public listing data from DailyDose.de by listing ID. Returns title, description, price, location, and image URLs.',
    'parameters': {
        'listing_id': {
            'type': 'string',
            'description': "Numeric listing ID — the 'ai' query parameter from detail.htm?ai=XXXXX",
        },
    },
}

router = APIRouter(prefix='/dailydose/fetch', tags=['dailydose'])


class FetchRequest(BaseModel):
    listing_id: str


@router.get('/')
def describe() -> dict:
    return TOOL_DESCRIPTION


@router.post('/')
def run(request: FetchRequest) -> dict:
    return _run(request.listing_id)


def _run(listing_id: str) -> dict:
    url = f'{BASE_URL}/kleinanzeigen/detail.htm?ai={listing_id}'
    session = make_session()
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return _parse(BeautifulSoup(response.text, 'html.parser'), listing_id, url)


def _parse(soup: BeautifulSoup, listing_id: str, url: str) -> dict:
    title = _first_text(soup, ['h1', '.sitetitle', '#sitetitle', 'h2']) or ''
    description = _first_text(soup, ['.sitedescription', '#sitedescription', '.description']) or ''
    price = _labeled_value(soup, ['preis', 'price']) or _first_text(soup, ['.preis', '.price']) or ''
    location = _labeled_value(soup, ['ort', 'location']) or _first_text(soup, ['.ort', '.location']) or ''
    zip_code = _labeled_value(soup, ['plz', 'postleitzahl']) or _first_text(soup, ['.plz']) or ''

    image_urls: list[str] = []
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if 'windsurfen' in src or listing_id in src:
            full = urljoin(BASE_URL, src.split('?')[0])
            if full not in image_urls:
                image_urls.append(full)

    return {
        'id': listing_id,
        'url': url,
        'title': title,
        'description': description,
        'price': price,
        'zip_code': zip_code,
        'location': location,
        'image_urls': image_urls,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def fetch_listing(listing_id: str) -> dict:
        """Fetch public listing data from DailyDose.de. listing_id is the numeric 'ai' value from detail.htm?ai=XXXXX."""
        return _run(listing_id)


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(' ', strip=True)
            if text:
                return text
    return None


def _labeled_value(soup: BeautifulSoup, labels: list[str]) -> str | None:
    for label in labels:
        for node in soup.find_all(string=re.compile(label, re.IGNORECASE)):
            sibling = node.parent.find_next_sibling() if node.parent else None
            if sibling:
                text = sibling.get_text(' ', strip=True)
                if text:
                    return text
    return None
