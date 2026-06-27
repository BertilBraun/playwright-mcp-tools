from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import dailydose

load_dotenv(Path(__file__).parent / '.env')

mcp = FastMCP('Daily Dose MCP')

for service in dailydose.services:
    service.register(mcp)

if __name__ == '__main__':
    mcp.run(transport='stdio')
