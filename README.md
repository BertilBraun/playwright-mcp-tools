# MCPs

A collection of MCP (Model Context Protocol) services, each also exposed as a plain REST API for manual use.

## Structure

Each site or integration lives in its own subdirectory:

```text
mcp_server.py         - combined stdio MCP entry point
mcp_kleinanzeigen.py  - Kleinanzeigen-only stdio MCP entry point
mcp_dailydose.py      - DailyDose-only stdio MCP entry point
run_all.py            - FastAPI REST UI on :8000
dailydose/            - DailyDose.de windsurfing classifieds
  scrape.py           - scrape a category to CSV
  fetch.py            - fetch a public listing by ID
  post.py             - post a new listing
  delete.py           - delete a listing
  shared/
    auth.py           - Playwright login
    http_session.py   - rate-limited requests session
kleinanzeigen/        - Kleinanzeigen.de classifieds
  post.py             - fill in listing text fields; add photos manually
  shared/
    auth.py           - Playwright login
    log.py            - stderr logger for clean MCP stdio
```

## Setup

**With uv (recommended):**

```powershell
uv sync
```

**With pip:**

```powershell
pip install .
```

**Then:**

```powershell
playwright install chromium
Copy-Item .env.example .env
```

Fill in credentials in `.env`.

## Running the REST UI

```powershell
python run_all.py
```

Opens an interactive form UI at <http://localhost:8000> where you can invoke any tool manually. Reloads automatically on code changes.

## MCP Config

Prefer separate MCP server entries so clients can discover each service family directly:

```json
{
  "mcpServers": {
    "kleinanzeigen": {
      "command": "uv",
      "args": ["--directory", "/path/to/MCPs", "run", "mcp_kleinanzeigen.py"]
    },
    "daily-dose": {
      "command": "uv",
      "args": ["--directory", "/path/to/MCPs", "run", "mcp_dailydose.py"]
    }
  }
}
```

`mcp_server.py` still registers all services together if you want the old combined server.

## Adding a New Service

1. Create `<site>/` with the same layout: one file per tool, and a `shared/` directory for auth and utilities.
2. Each tool file must export:
   - `router` - an `APIRouter` for REST
   - `TOOL_DESCRIPTION` - metadata with `name`, `endpoint`, `description`, and `parameters`
   - `register(mcp)` - registers the tool with a `FastMCP` instance
   - `_run(...)` - the implementation called by both the router and `register`
3. Add the module to `services` in `<site>/__init__.py`; `run_all.py` and the matching MCP entry point pick it up automatically.

## Environment Variables

See `.env.example`. Credentials are never committed.
