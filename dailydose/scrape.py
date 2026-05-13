import io
import re
from typing import Literal, get_args
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import pandas as pd
from bs4 import BeautifulSoup
from fastapi import APIRouter
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from dailydose.shared.http_session import make_session

BASE_URL = 'https://www.dailydose.de'
TOTAL_PAGES_RE = re.compile(r'Seite\s+\d+\s+von\s+(\d+)', re.IGNORECASE)

Category = Literal[
    'finnen',
    'foils',
    'windsurfgabeln',
    'windsurfmasten',
    'windsurfsegel',
    'windsurfboards',
    'surfzubehoer',
]
VALID_CATEGORIES: list[str] = list(get_args(Category))

TOOL_DESCRIPTION = {
    'name': 'scrape_category',
    'endpoint': '/dailydose/scrape/',
    'description': 'Scrape a DailyDose.de category and return listings as CSV (columns: id, title, price_eur, url), sorted by price ascending.',
    'parameters': {
        'category': {
            'type': 'string',
            'enum': VALID_CATEGORIES,
            'description': 'Category slug to scrape',
        },
        'max_pages': {
            'type': 'integer',
            'default': 0,
            'description': 'Maximum pages to fetch; 0 means all pages',
        },
        'sleep': {
            'type': 'number',
            'default': 1.0,
            'description': 'Seconds to wait between page requests',
        },
    },
}

router = APIRouter(prefix='/dailydose/scrape', tags=['dailydose'])


class ScrapeRequest(BaseModel):
    category: Category
    max_pages: int = 0
    sleep: float = 1.0


@router.get('/')
def describe() -> dict:
    return TOOL_DESCRIPTION


@router.post('/')
def run(request: ScrapeRequest) -> str:
    return _run(request.category, request.max_pages, request.sleep)


def _run(category: str, max_pages: int = 0, sleep: float = 1.0) -> str:
    category_url = f'{BASE_URL}/kleinanzeigen/{category}.htm'
    session = make_session(min_interval=sleep)

    first_url = _with_query(category_url, cf='kk', pg=1)
    response = session.get(first_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    ci = _detect_ci(soup)
    if not ci:
        raise RuntimeError("Could not detect pagination 'ci' parameter from page 1.")

    total_pages = _parse_total_pages(soup) or 999_999
    if max_pages > 0:
        total_pages = min(total_pages, max_pages)

    rows: list[dict] = []
    seen: set[str] = set()

    for page_number in range(1, total_pages + 1):
        page_url = _with_query(category_url, cf='kk', ci=ci, pg=page_number)
        resp = session.get(page_url, timeout=30)
        resp.raise_for_status()
        sp = BeautifulSoup(resp.text, 'html.parser')

        links = sp.select('a[href*="detail.htm?ai="]')
        if not links:
            break

        for anchor in links:
            href = anchor.get('href', '')
            title = anchor.get_text(' ', strip=True)
            if not href or not title:
                continue

            id_match = re.search(r'ai=(\d+)', href)
            if not id_match:
                continue
            listing_id = id_match.group(1)

            url = urljoin(category_url, href)
            if url in seen:
                continue
            seen.add(url)

            price_raw = _extract_price_near_link(anchor)
            rows.append(
                {
                    'id': listing_id,
                    'title': title,
                    'price_eur': _normalize_price(price_raw or ''),
                    'url': url,
                }
            )

    df = pd.DataFrame(rows).drop_duplicates(subset=['url'])
    df = df.sort_values(['price_eur', 'title'], ascending=[True, True], na_position='last').reset_index(drop=True)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def scrape_category(category: Category, max_pages: int = 0, sleep: float = 1.0) -> str:
        """Scrape a DailyDose.de category. Returns CSV with columns: id, title, price_eur, url — sorted by price. Valid categories: finnen, foils, windsurfgabeln, windsurfmasten, windsurfsegel, windsurfboards, surfzubehoer"""
        return _run(category, max_pages, sleep)


def _with_query(url: str, **params: object) -> str:
    parts = urlparse(url)
    query = parse_qs(parts.query)
    for key, value in params.items():
        query[key] = [str(value)]
    return urlunparse(
        (parts.scheme, parts.netloc, parts.path, parts.params, urlencode(query, doseq=True), parts.fragment)
    )


def _parse_total_pages(soup: BeautifulSoup) -> int | None:
    m = TOTAL_PAGES_RE.search(soup.get_text(' ', strip=True))
    return int(m.group(1)) if m else None


def _detect_ci(soup: BeautifulSoup) -> str | None:
    for anchor in soup.select('a[href*="cf=kk"][href*="ci="][href*="pg="]'):
        query = parse_qs(urlparse(anchor.get('href', '')).query)
        if 'ci' in query and query['ci']:
            return query['ci'][0]
    return None


def _normalize_price(price_raw: str) -> float | None:
    if not price_raw:
        return None
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*€?\s*[-–]\s*\d+', price_raw)
    if m:
        try:
            return float(m.group(1).replace(',', '.'))
        except ValueError:
            pass
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*€|€\s*(\d+(?:[.,]\d+)?)', price_raw)
    if m:
        try:
            return float((m.group(1) or m.group(2)).replace(',', '.'))
        except ValueError:
            return None
    m = re.search(r'\b(\d{2,6})\b', price_raw)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _extract_price_near_link(anchor) -> str | None:
    title = anchor.get_text(' ', strip=True)
    for text in anchor.parent.stripped_strings:
        if text == title:
            continue
        if (
            '€' in text
            or re.search(r'\bVB\b|\bVHB\b|[-–]\s*\d', text, re.IGNORECASE)
            or re.search(r'\d+\s*[-–]\s*\d+', text)
        ):
            return text.strip()
    node = anchor
    for _ in range(14):
        node = node.find_next()
        if node is None:
            break
        text = node.get_text(' ', strip=True)
        if not text:
            continue
        if '€' in text or re.search(r'\bVB\b|\bVHB\b', text, re.IGNORECASE) or re.search(r'\d+\s*[-–]\s*\d+', text):
            return text.strip()[:120]
    return None
