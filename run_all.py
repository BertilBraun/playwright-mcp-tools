import asyncio
import threading

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from mcp.server.fastmcp import FastMCP

from dailydose import delete, fetch, post, scrape

load_dotenv()

mcp = FastMCP('DailyDose Tools', host='0.0.0.0', port=8001)
scrape.register(mcp)
fetch.register(mcp)
post.register(mcp)
delete.register(mcp)

app = FastAPI(title='MCP Services')
app.include_router(scrape.router)
app.include_router(fetch.router)
app.include_router(post.router)
app.include_router(delete.router)

_SERVICES = [scrape, fetch, post, delete]

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MCP Services</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 860px; margin: 48px auto; padding: 0 24px; color: #1a1a1a; }
    h1 { font-size: 1.5rem; margin-bottom: 4px; }
    .subtitle { color: #666; margin-bottom: 36px; font-size: 0.9rem; }
    .card { border: 1px solid #e0e0e0; border-radius: 10px; padding: 24px; margin-bottom: 20px; }
    .card h2 { margin: 0 0 8px; font-size: 1rem; font-family: monospace; color: #0057b7; }
    .card .desc { color: #333; margin-bottom: 14px; line-height: 1.5; font-size: 0.95rem; }
    .params { display: flex; flex-direction: column; gap: 5px; }
    .param { background: #f5f5f5; border-radius: 6px; padding: 8px 12px; font-size: 0.82rem; }
    .pname { font-family: monospace; font-weight: bold; color: #1a1a1a; }
    .ptype { font-family: monospace; color: #888; }
    .pdesc { color: #555; }
    .penum { font-family: monospace; color: #666; font-size: 0.78rem; display: block; margin-top: 2px; }
    .endpoints { margin-top: 14px; font-size: 0.8rem; color: #999; font-family: monospace; }
  </style>
</head>
<body>
  <h1>MCP Services</h1>
  <p class="subtitle">
    REST API: <strong>http://localhost:8000</strong>
    &nbsp;|&nbsp;
    MCP (SSE): <strong>http://localhost:8001/sse</strong>
  </p>
  {{CARDS}}
</body>
</html>"""


@app.get('/', response_class=HTMLResponse)
def overview() -> str:
    cards = '\n'.join(_render_card(svc.TOOL_DESCRIPTION) for svc in _SERVICES)
    return _HTML_TEMPLATE.replace('{{CARDS}}', cards)


def _render_card(desc: dict) -> str:
    name = desc['name']
    description = desc['description']
    params = desc.get('parameters', {})
    action = name.split('_')[0]
    prefix = f'/dailydose/{action}'

    param_items: list[str] = []
    for param_name, param_info in params.items():
        type_str = param_info.get('type', 'string')
        default = f' = {param_info["default"]}' if 'default' in param_info else ''
        param_desc = param_info.get('description', '')
        enum_html = ''
        if 'enum' in param_info:
            enum_html = f'<span class="penum">options: {", ".join(param_info["enum"])}</span>'
        param_items.append(
            f'<div class="param">'
            f'<span class="pname">{param_name}</span>'
            f'<span class="ptype">: {type_str}{default}</span>'
            f' <span class="pdesc">— {param_desc}</span>'
            f'{enum_html}'
            f'</div>'
        )

    params_html = '\n'.join(param_items)
    return (
        f'<div class="card">\n'
        f'  <h2>{name}</h2>\n'
        f'  <p class="desc">{description}</p>\n'
        f'  <div class="params">{params_html}</div>\n'
        f'  <div class="endpoints">'
        f'GET {prefix}/ → description &nbsp;|&nbsp; POST {prefix}/ → run'
        f'</div>\n'
        f'</div>'
    )


def _start_mcp() -> None:
    mcp.run(transport='sse')


async def _serve() -> None:
    mcp_thread = threading.Thread(target=_start_mcp, daemon=True)
    mcp_thread.start()
    print('MCP SSE server starting on http://localhost:8001/sse')

    config = uvicorn.Config(app, host='0.0.0.0', port=8000, log_level='info')
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == '__main__':
    asyncio.run(_serve())
