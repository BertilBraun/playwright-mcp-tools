# MCPs

A collection of MCP (Model Context Protocol) services, each also exposed as a plain REST API for manual use.

## Structure

Each site or integration lives in its own subdirectory with its own `shared/` module:

```text
run_all.py          — single entry point: REST on :8000, MCP SSE on :8001
dailydose/          — DailyDose.de windsurfing classifieds
  scrape.py         — scrape a category → CSV
  fetch.py          — fetch a public listing by ID
  post.py           — post a new listing
  delete.py         — delete a listing
  shared/
    auth.py         — Playwright login
    http_session.py — rate-limited requests session
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

## Running

```bash
python run_all.py
```

- REST overview: <http://localhost:8000>
- MCP SSE endpoint: <http://localhost:8001/sse>

## Claude Desktop config

```json
{
  "mcpServers": {
    "dailydose": { "url": "http://localhost:8001/sse" }
  }
}
```

## Adding a new service

1. Create `<site>/` with the same layout: `shared/`, one file per tool
2. Each tool file exports `router`, `TOOL_DESCRIPTION`, `_run()`, and `register(mcp)`
3. Add two lines to `run_all.py`: `app.include_router(...)` and `<module>.register(mcp)`

## Environment variables

See `.env.example`. Credentials are never committed.
