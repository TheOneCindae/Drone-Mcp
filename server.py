import time
from pymavlink import mavutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pixhawk-mcp")

def connect() -> mavutil.mavfile:
    conn = mavutil.mavlink_connection("/dev/ttyUSB0", baud=57600)
    conn.wait_heartbeat()
    return conn


# ── Helpers ───────────────────────────────────────────────────────────────────

def _send_cmd(conn: mavutil.mavfile, cmd: int, *params) -> str:
    p = list(params) + [0] * (7 - len(params))
    conn.mav.command_long_send(conn.target_system, conn.target_component, cmd, 0, *p[:7])
    ack = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=5)
    if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return "accepted"
    return f"rejected (result={ack.result if ack else 'timeout'})"


def _wait_for_alt(conn: mavutil.mavfile, target_m: float, tolerance: float = 0.5, timeout: float = 30):
    deadline = time.time() + timeout
    msg = None
    while time.time() < deadline:
        msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
        if msg and abs(msg.relative_alt / 1000 - target_m) < tolerance:
            return msg, True
    return msg, False


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_telemetry() -> dict:
    """Return current altitude (m), heading (deg), and battery voltage (V)."""
    conn = connect()

    alt_msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=5)
    att_msg = conn.recv_match(type="VFR_HUD", blocking=True, timeout=5)
    bat_msg = conn.recv_match(type="SYS_STATUS", blocking=True, timeout=5)

    return {
        "altitude_m":       round(alt_msg.relative_alt / 1000, 2) if alt_msg else None,
        "heading_deg":      att_msg.heading if att_msg else None,
        "battery_voltage_v": round(bat_msg.voltage_battery / 1000, 2) if bat_msg else None,
    }


@mcp.tool()
def arm_disarm(arm: bool) -> str:
    """
    Arm or disarm the drone.

    Args:
        arm: True to arm, False to disarm.
    """
    conn = connect()
    result = _send_cmd(conn, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1 if arm else 0)
    if result == "accepted":
        return "armed" if arm else "disarmed"
    return f"command {result}"


@mcp.tool()
def set_mode(mode: str) -> str:
    """
    Set the flight mode.

    Args:
        mode: Mode name, e.g. GUIDED, LOITER, RTL, LAND, STABILIZE, ALT_HOLD.
    """
    conn = connect()
    mode_id = conn.mode_mapping().get(mode.upper())
    if mode_id is None:
        return f"unknown mode '{mode}'"
    conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)
    ack = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=5)
    if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return f"mode set to {mode.upper()}"
    return f"mode change {ack.result if ack else 'timeout'}"


@mcp.tool()
def goto(lat: float, lon: float, altitude_m: float) -> str:
    """
    Fly to a GPS coordinate at the given altitude (requires GUIDED mode).

    Args:
        lat: Target latitude in decimal degrees.
        lon: Target longitude in decimal degrees.
        altitude_m: Target altitude above home in metres.
    """
    conn = connect()
    conn.mav.send(mavutil.mavlink.MAVLink_set_position_target_global_int_message(
        0,
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000,  # position only
        int(lat * 1e7), int(lon * 1e7), altitude_m,
        0, 0, 0, 0, 0, 0, 0, 0,
    ))
    return f"heading to ({lat}, {lon}) at {altitude_m} m"


@mcp.tool()
def land() -> str:
    """Command the drone to land at the current position."""
    conn = connect()
    result = _send_cmd(conn, mavutil.mavlink.MAV_CMD_NAV_LAND)
    return f"land command {result}"


# ── Skill ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def takeoff_and_hover(target_altitude_m: float = 5.0) -> str:
    """
    Arm the drone, switch to GUIDED mode, take off to target altitude, and hover.

    Args:
        target_altitude_m: Desired hover altitude in metres (default 5 m).
    """
    conn = connect()

    # 1. Set GUIDED mode
    conn.mav.set_mode_send(
        conn.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        4,  # GUIDED mode number for ArduPilot
    )
    time.sleep(1)

    # 2. Arm
    _send_cmd(conn, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    time.sleep(2)

    # 3. Takeoff
    _send_cmd(conn, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, target_altitude_m)

    # 4. Wait until target altitude is reached (±0.5 m)
    msg, reached = _wait_for_alt(conn, target_altitude_m)
    if reached:
        return f"hovering at {target_altitude_m} m"
    return f"takeoff timeout — last alt {msg.relative_alt / 1000:.1f} m" if msg else "no position data"


@mcp.tool()
def return_to_launch() -> str:
    """Switch to RTL mode and wait for the drone to land at the home position."""
    conn = connect()
    mode_id = conn.mode_mapping().get("RTL")
    if mode_id is None:
        return "RTL mode not available"
    conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)
    # Wait until altitude drops to near zero (landed)
    msg, landed = _wait_for_alt(conn, 0.0, tolerance=1.0, timeout=60)
    if landed:
        return "landed at home"
    return f"RTL timeout — last alt {msg.relative_alt / 1000:.1f} m" if msg else "no position data"


if __name__ == "__main__":
    mcp.run()
