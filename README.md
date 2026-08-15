# Pixhawk MCP Server

Control a Pixhawk/ArduPilot drone through natural language using any MCP-compatible LLM.

---

## How It Works

```
LLM (Claude / Copilot / etc.)
        │  MCP protocol (JSON-RPC over stdio or SSE)
        ▼
  server.py  (FastMCP)
        │  MAVLink over serial / UDP
        ▼
  Pixhawk flight controller
```

The MCP server exposes drone actions as tools. The LLM calls those tools in response to natural language commands like *"take off to 10 metres"* or *"fly to these coordinates"*.

---

## Hardware Connection

### Option 1 — USB (recommended for ground testing)

Connect the Pixhawk's micro-USB port directly to your computer.

| What | Value |
|------|-------|
| Port (Linux) | `/dev/ttyUSB0` or `/dev/ttyACM0` |
| Port (Windows) | `COM3`, `COM4`, … (check Device Manager) |
| Baud rate | `115200` |

### Option 2 — Telemetry Radio (SiK / RFD900)

Plug the ground-side radio into USB. The Pixhawk side connects to **TELEM1**.

| What | Value |
|------|-------|
| Port | same as USB above |
| Baud rate | `57600` (default SiK baud) |

### Option 3 — UDP over companion computer (Raspberry Pi / Jetson)

Run MAVProxy or MAVROS on the companion computer to bridge the serial link to UDP, then point the server at the network.

```
Pixhawk TELEM2  →  companion computer (serial)  →  UDP 14550
```

---

## Updating the Connection String

Edit the `connect()` function in `server.py` to match your setup:

```python
# USB on Linux
conn = mavutil.mavlink_connection("/dev/ttyUSB0", baud=115200)

# USB on Windows
conn = mavutil.mavlink_connection("COM4", baud=115200)

# Telemetry radio (Linux)
conn = mavutil.mavlink_connection("/dev/ttyUSB0", baud=57600)

# UDP (companion computer or simulator)
conn = mavutil.mavlink_connection("udpin:0.0.0.0:14550")

# TCP
conn = mavutil.mavlink_connection("tcp:192.168.1.100:5760")
```

---

## Installation

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

`requirements.txt`:
```
pymavlink
mcp[cli]
```

---

## Running the Server

### stdio mode (default — used by most LLM desktop clients)

```bash
python server.py
```

The server speaks JSON-RPC over stdin/stdout. The LLM client launches this process directly.

### SSE mode (HTTP — used for remote or web-based clients)

```bash
fastmcp run server.py --transport sse --port 8000
```

The server is now reachable at `http://localhost:8000/sse`.

---

## Connecting to an LLM

### Claude Desktop (Anthropic)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "pixhawk": {
      "command": "python",
      "args": ["/path/to/Drone-Mcp/server.py"]
    }
  }
}
```

Restart Claude Desktop. A drone icon will appear in the toolbar confirming the tools are loaded.

---

### VS Code — GitHub Copilot (Agent mode)

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "pixhawk": {
      "type": "stdio",
      "command": "python",
      "args": ["${workspaceFolder}/server.py"]
    }
  }
}
```

Open Copilot Chat, switch to **Agent** mode, and the drone tools will be available.

---

### Cursor

Open **Settings → MCP** and add a new server:

```json
{
  "pixhawk": {
    "command": "python",
    "args": ["/path/to/Drone-Mcp/server.py"]
  }
}
```

---

### Any client via SSE (remote / web)

Start the server in SSE mode (see above), then point your client at:

```
http://localhost:8000/sse
```

For LangChain / LlamaIndex / custom clients, use the `mcp` Python SDK:

```python
from mcp.client.sse import sse_client

async with sse_client("http://localhost:8000/sse") as (read, write):
    # list tools, call tools, etc.
    ...
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `get_telemetry` | Returns altitude (m), heading (°), battery voltage (V) |
| `arm_disarm` | Arms or disarms the drone |
| `set_mode` | Sets flight mode: GUIDED, LOITER, RTL, LAND, STABILIZE, ALT_HOLD |
| `goto` | Flies to a GPS coordinate at a given altitude (GUIDED mode required) |
| `land` | Commands landing at the current position |
| `takeoff_and_hover` | Arms → GUIDED → takeoff → hovers at target altitude |
| `return_to_launch` | Switches to RTL and waits until landed at home |

---

## Testing Without Hardware — SITL Simulator

ArduPilot's Software In The Loop (SITL) lets you test everything without a real drone.

**1. Install ArduPilot SITL**

```bash
git clone https://github.com/ArduPilot/ardupilot.git
cd ardupilot
Tools/environment_install/install-prereqs-ubuntu.sh -y
./waf configure --board sitl
./waf copter
```

**2. Launch the simulator**

```bash
cd ArduCopter
sim_vehicle.py -v ArduCopter --console --map
```

SITL listens on UDP 14550 by default.

**3. Point the server at SITL**

```python
conn = mavutil.mavlink_connection("udpin:0.0.0.0:14550")
```

**4. Run the server and talk to your LLM normally** — all commands execute in the simulator.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `wait_heartbeat()` hangs | Wrong port or baud rate. Check Device Manager (Windows) or `ls /dev/tty*` (Linux) |
| `Permission denied /dev/ttyUSB0` | `sudo usermod -aG dialout $USER` then log out and back in |
| `command rejected` on arm | Drone is not in GUIDED mode, or pre-arm checks are failing (check Mission Planner) |
| LLM doesn't see tools | Config file path is wrong, or Python is not on PATH — use the full path to the Python executable |
| `goto` has no effect | Drone must be in GUIDED mode first — call `set_mode("GUIDED")` before `goto` |

---

## Safety Notes

- Always test with SITL before flying with real hardware.
- Keep a human pilot with a physical RC transmitter ready to take manual override at all times.
- The `arm_disarm` and `takeoff_and_hover` tools send real MAVLink commands — ensure the area is clear before running them.
- Set a sensible `FS_THR_ENABLE` failsafe in Mission Planner so the drone lands safely if the connection drops.
