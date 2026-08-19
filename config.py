"""
Centralized, environment-overridable configuration for the pixhawk-mcp server.
Nothing here has side effects — safe to import from anywhere.
"""

import os
from pathlib import Path

# udpin:0.0.0.0:14550 is the common default for ArduPilot/PX4 SITL broadcasting
# telemetry out. It works, but being connectionless UDP it can't tell a dead
# link from a quiet one, and if more than one process binds the same port,
# incoming packets get split between them unpredictably (this is what caused
# the original "sometimes connects, sometimes hangs" symptom, compounded by
# stray duplicate server processes never being cleaned up).
#
# More reliable alternatives, if your simulator supports them:
#   - TCP, e.g. "tcp:127.0.0.1:5762" (ArduPilot SITL's default TCP port). TCP
#     is connection-oriented: a dropped link fails fast with a socket error
#     instead of silently going stale, and there's no multi-listener ambiguity.
#   - udpout instead of udpin, if the simulator can be told to connect out to
#     a fixed client rather than broadcasting for anyone to pick up.
#   - Routing through mavlink-router or MAVProxy, which owns the single real
#     connection to the vehicle and fans it out to multiple local endpoints
#     (this server, QGroundControl/Mission Planner, etc.) — this avoids
#     several processes/apps all racing to bind the same UDP port directly.
MAVLINK_ENDPOINT = os.environ.get("MAVLINK_ENDPOINT", "udpin:0.0.0.0:14550")

HEARTBEAT_TIMEOUT_S = float(os.environ.get("MAVLINK_HEARTBEAT_TIMEOUT", "10"))
CMD_ACK_TIMEOUT_S = float(os.environ.get("MAVLINK_CMD_TIMEOUT", "5"))
RECONNECT_MAX_RETRIES = int(os.environ.get("MAVLINK_RECONNECT_RETRIES", "3"))
RECONNECT_BACKOFF_S = float(os.environ.get("MAVLINK_RECONNECT_BACKOFF", "2"))

LOG_LEVEL = os.environ.get("PIXHAWK_MCP_LOG_LEVEL", "INFO").upper()
LOG_FILE = Path(os.environ.get("PIXHAWK_MCP_LOG_FILE", str(Path(__file__).with_name("pixhawk_mcp.log"))))
LOCK_FILE = Path(os.environ.get("PIXHAWK_MCP_LOCK_FILE", str(Path(__file__).with_name(".pixhawk_mcp.lock"))))
