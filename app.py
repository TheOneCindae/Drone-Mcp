"""The shared FastMCP instance, imported by tools.py and skills.py to register
against with @mcp.tool(), and by server.py to run."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pixhawk-mcp")
