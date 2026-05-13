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
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 860px; margin: 48px auto; padding: 0 24px; color: #1a1a1a; }
    h1 { font-size: 1.5rem; margin-bottom: 4px; }
    .subtitle { color: #666; margin-bottom: 36px; font-size: 0.9rem; }

    .card { border: 1px solid #e0e0e0; border-radius: 10px; padding: 24px; margin-bottom: 20px; }
    .card h2 { margin: 0 0 6px; font-size: 1rem; font-family: monospace; color: #0057b7; }
    .card .desc { color: #333; margin: 0 0 18px; line-height: 1.5; font-size: 0.95rem; }

    .form-grid { display: flex; flex-direction: column; gap: 10px; }
    .field { display: grid; grid-template-columns: 160px 1fr; gap: 8px; align-items: start; }
    .field label { font-family: monospace; font-size: 0.85rem; font-weight: bold; padding-top: 6px; }
    .field label .ftype { font-weight: normal; color: #888; }
    .field input, .field select, .field textarea {
      width: 100%; padding: 5px 8px; border: 1px solid #ccc; border-radius: 5px;
      font-size: 0.88rem; font-family: inherit; background: #fafafa;
    }
    .field textarea { resize: vertical; min-height: 64px; }
    .field .fdesc { font-size: 0.78rem; color: #777; grid-column: 2; margin-top: -4px; }

    .run-btn {
      margin-top: 12px; padding: 7px 20px; background: #0057b7; color: #fff;
      border: none; border-radius: 6px; font-size: 0.9rem; cursor: pointer;
    }
    .run-btn:hover { background: #004494; }
    .run-btn:disabled { background: #aaa; cursor: default; }

    .result { margin-top: 16px; }
    .result pre {
      background: #f4f4f4; border: 1px solid #ddd; border-radius: 6px;
      padding: 12px; font-size: 0.8rem; white-space: pre-wrap; word-break: break-all;
      max-height: 400px; overflow-y: auto; margin: 0;
    }
    .result.error pre { background: #fff4f4; border-color: #f5b7b7; color: #c00; }
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
  <script>
    document.querySelectorAll('.tool-form').forEach(form => {
      form.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = form.querySelector('.run-btn');
        const resultDiv = form.querySelector('.result');
        const resultPre = resultDiv.querySelector('pre');

        btn.disabled = true;
        btn.textContent = 'Running…';
        resultDiv.className = 'result';
        resultPre.textContent = '';
        resultDiv.style.display = 'block';

        const body = {};
        form.querySelectorAll('[data-param]').forEach(el => {
          const name = el.dataset.param;
          const kind = el.dataset.kind;
          if (kind === 'integer') {
            body[name] = parseInt(el.value, 10);
          } else if (kind === 'number') {
            body[name] = parseFloat(el.value);
          } else if (kind === 'array') {
            body[name] = el.value.split('\\n').map(s => s.trim()).filter(Boolean);
          } else {
            body[name] = el.value;
          }
        });

        try {
          const resp = await fetch(form.dataset.endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
          const text = await resp.text();
          let display;
          try { display = JSON.stringify(JSON.parse(text), null, 2); }
          catch { display = text; }
          if (!resp.ok) resultDiv.className = 'result error';
          resultPre.textContent = display;
        } catch (err) {
          resultDiv.className = 'result error';
          resultPre.textContent = 'Network error: ' + err.message;
        } finally {
          btn.disabled = false;
          btn.textContent = 'Run';
        }
      });
    });
  </script>
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
        f'    <button class="run-btn" type="submit">Run</button>\n'
        f'    <div class="result" style="display:none"><pre></pre></div>\n'
        f'  </form>\n'
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
