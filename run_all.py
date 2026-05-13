import argparse
import asyncio
import threading
from itertools import groupby
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from mcp.server.fastmcp import FastMCP

from dailydose import delete, fetch, post, scrape

load_dotenv()

app = FastAPI(title='MCP Services')
app.include_router(scrape.router)
app.include_router(fetch.router)
app.include_router(post.router)
app.include_router(delete.router)

_SERVICES = [scrape, fetch, post, delete]
_TEMPLATE = (Path(__file__).parent / 'templates' / 'index.html').read_text(encoding='utf-8')


@app.get('/', response_class=HTMLResponse)
def overview() -> str:
    sorted_services = sorted(_SERVICES, key=lambda m: m.__package__ or '')
    sections = []
    for category, group in groupby(sorted_services, key=lambda m: m.__package__ or 'other'):
        services = list(group)
        sections.append(_render_section(category, services))
    return _TEMPLATE.replace('{{SECTIONS}}', '\n'.join(sections))


def _render_section(category: str, services: list) -> str:
    cards = [_render_card(svc.TOOL_DESCRIPTION) for svc in services]
    cards_html = '\n'.join(cards)
    count = len(cards)
    noun = 'tool' if count == 1 else 'tools'
    return (
        f'<details class="category" open>\n'
        f'  <summary>{category} <span class="count">({count} {noun})</span></summary>\n'
        f'  <div class="category-tools">\n{cards_html}\n  </div>\n'
        f'</details>'
    )


def _render_card(desc: dict) -> str:
    name = desc['name']
    description = desc['description']
    params = desc.get('parameters', {})
    action = name.split('_')[0]
    endpoint = f'/dailydose/{action}/'

    fields: list[str] = []
    for param_name, param_info in params.items():
        kind = param_info.get('type', 'string')
        param_desc = param_info.get('description', '')
        default = param_info.get('default', '')

        label = f'<label>{param_name} <span class="ftype">:{kind}</span></label>'

        if 'enum' in param_info:
            options = ''.join(
                f'<option value="{v}"{"selected" if v == default else ""}>{v}</option>' for v in param_info['enum']
            )
            control = f'<select data-param="{param_name}" data-kind="string">{options}</select>'
        elif kind == 'array':
            control = (
                f'<textarea data-param="{param_name}" data-kind="array" placeholder="one item per line"></textarea>'
            )
        elif kind in ('integer', 'number'):
            step = '' if kind == 'integer' else ' step="any"'
            control = f'<input type="number" data-param="{param_name}" data-kind="{kind}" value="{default}"{step}>'
        else:
            control = f'<input type="text" data-param="{param_name}" data-kind="string" value="{default}">'

        fdesc = f'<span class="fdesc">{param_desc}</span>' if param_desc else ''
        fields.append(f'<div class="field">{label}<div>{control}{fdesc}</div></div>')

    fields_html = '\n'.join(fields)
    return (
        f'<div class="card">\n'
        f'  <h2>{name}</h2>\n'
        f'  <p class="desc">{description}</p>\n'
        f'  <form class="tool-form" data-endpoint="{endpoint}">\n'
        f'    <div class="form-grid">{fields_html}</div>\n'
        f'    <button class="run-btn" type="submit">Run Test</button>\n'
        f'    <div class="result" style="display:none"><pre></pre></div>\n'
        f'  </form>\n'
        f'</div>'
    )


def _start_mcp() -> None:
    mcp = FastMCP('DailyDose Tools', host='0.0.0.0', port=8001)
    scrape.register(mcp)
    fetch.register(mcp)
    post.register(mcp)
    delete.register(mcp)
    mcp.run(transport='sse')


async def _serve(production: bool) -> None:
    if production:
        mcp_thread = threading.Thread(target=_start_mcp, daemon=True)
        mcp_thread.start()
        print('MCP SSE server starting on http://localhost:8001/sse')
        config = uvicorn.Config(app, host='0.0.0.0', port=8000, log_level='info')
    else:
        print('Dev mode: MCP server disabled, reload enabled')
        config = uvicorn.Config('run_all:app', host='0.0.0.0', port=8000, log_level='info', reload=True)

    await uvicorn.Server(config).serve()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    asyncio.run(_serve(args.production))
