from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import dailydose
import kleinanzeigen

load_dotenv()

mcp = FastMCP('MCP Services')

for _svc in dailydose.services + kleinanzeigen.services:
    _svc.register(mcp)

if __name__ == '__main__':
    mcp.run(transport='stdio')
