"""
Logging setup. Import and call configure() once, before anything else logs.

stdout is reserved for the MCP JSON-RPC protocol — never log there. stderr is
also not reliably surfaced by every MCP client, so a rotating log file is the
one place that's always inspectable, e.g.:
  PowerShell : Get-Content pixhawk_mcp.log -Wait -Tail 20
  bash       : tail -f pixhawk_mcp.log
"""

import logging
import logging.handlers
import sys

import config

logger = logging.getLogger("pixhawk-mcp")


def configure() -> None:
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE, mode="a", encoding="utf-8", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    stream_handler = logging.StreamHandler(sys.stderr)

    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        handlers=[stream_handler, file_handler],
        force=True,
    )
    # pymavlink/pyserial are extremely chatty at DEBUG; keep them at INFO regardless.
    logging.getLogger("pymavlink").setLevel(max(logging.INFO, logging.getLogger().level))
