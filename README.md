# MCPs

A collection of MCP (Model Context Protocol) services, each also exposed as a plain REST API for manual use.

## Structure

Each site or integration lives in its own subdirectory:

```text
mcp_server.py       — stdio MCP entry point for Claude Desktop
run_all.py          — FastAPI REST UI on :8000
dailydose/          — DailyDose.de windsurfing classifieds
  scrape.py         — scrape a category → CSV
  fetch.py          — fetch a public listing by ID
  post.py           — post a new listing
  delete.py         — delete a listing
  shared/
    auth.py         — Playwright login
    http_session.py — rate-limited requests session
kleinanzeigen/      — Kleinanzeigen.de classifieds
  post.py           — fill in a listing form (browser stays open for review)
  shared/
    auth.py         — Playwright login
    log.py          — stderr logger (keeps stdout clean for MCP stdio)
```

## Setup

**With uv (recommended):**

```bash
uv sync
```

**With pip:**

```bash
pip install .
```

**Then:**

```bash
playwright install chromium
cp .env.example .env   # fill in credentials
```

## Running the REST UI

```bash
python run_all.py
```

Opens an interactive form UI at <http://localhost:8000> where you can invoke any tool manually. Reloads automatically on code changes.

## Claude Desktop config

`mcp_server.py` speaks MCP over stdio — no server to keep running.

```json
{
  "mcpServers": {
    "mcps": {
      "command": "uv",
      "args": ["--directory", "/path/to/MCPs", "run", "mcp_server.py"]
    }
  }
}
```

## Adding a new service

1. Create `<site>/` with the same layout: one file per tool, a `shared/` for auth/utils
2. Each tool file must export:
   - `router` — an `APIRouter` (for REST)
   - `TOOL_DESCRIPTION` — dict with `name`, `endpoint`, `description`, `parameters`
   - `register(mcp)` — registers the tool with a `FastMCP` instance
   - `_run(...)` — the actual implementation, called by both the router and `register`
3. Add the module to `services` in `<site>/__init__.py` — both `run_all.py` and `mcp_server.py` pick it up automatically

## Environment variables

See `.env.example`. Credentials are never committed.
