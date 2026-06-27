from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import kleinanzeigen

load_dotenv(Path(__file__).parent / '.env')

mcp = FastMCP('Kleinanzeigen MCP')

for service in kleinanzeigen.services:
    service.register(mcp)

if __name__ == '__main__':
    mcp.run(transport='stdio')
