"""Single-action MCP tools: read telemetry/position, arm/disarm, set mode,
fly to a point, land. Composite multi-step behaviors live in skills.py."""

import logging

from pymavlink import mavutil

import config
from app import mcp
from mavlink_client import connect, send_cmd, tool_guard

logger = logging.getLogger("pixhawk-mcp")


@mcp.tool()
@tool_guard
def get_telemetry() -> dict:
    """Return current GPS position, altitude, heading, and battery voltage."""
    logger.info("Tool call: get_telemetry")
    conn = connect()

    alt_msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=5)
    att_msg = conn.recv_match(type="VFR_HUD", blocking=True, timeout=5)
    bat_msg = conn.recv_match(type="SYS_STATUS", blocking=True, timeout=5)

    if not (alt_msg and att_msg and bat_msg):
        logger.warning(
            f"Incomplete telemetry: alt={'ok' if alt_msg else 'MISSING'} "
            f"att={'ok' if att_msg else 'MISSING'} bat={'ok' if bat_msg else 'MISSING'}"
        )

    result = {
        "lat": round(alt_msg.lat / 1e7, 7) if alt_msg else None,
        "lon": round(alt_msg.lon / 1e7, 7) if alt_msg else None,
        "altitude_m":       round(alt_msg.relative_alt / 1000, 2) if alt_msg else None,
        "heading_deg":      att_msg.heading if att_msg else None,
        "battery_voltage_v": round(bat_msg.voltage_battery / 1000, 2) if bat_msg else None,
    }
    logger.info(f"Telemetry: {result}")
    return result


@mcp.tool()
@tool_guard
def get_gps_position() -> dict:
    """
    Return the drone's current GPS position (lat/lon in decimal degrees,
    altitude in metres). Use this to get the drone's own coordinates when the
    caller wants to command a move but hasn't given a target latitude/longitude
    themselves — e.g. to hold, hover in place, or compute a position relative
    to where the drone already is.
    """
    logger.info("Tool call: get_gps_position")
    conn = connect()
    msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=5)
    if not msg:
        logger.warning("No GLOBAL_POSITION_INT received for get_gps_position")
        return {"lat": None, "lon": None, "altitude_m": None}

    result = {
        "lat": round(msg.lat / 1e7, 7),
        "lon": round(msg.lon / 1e7, 7),
        "altitude_m": round(msg.relative_alt / 1000, 2),
    }
    logger.info(f"GPS position: {result}")
    return result


@mcp.tool()
@tool_guard
def arm_disarm(arm: bool) -> str:
    """
    Arm or disarm the drone.

    Args:
        arm: True to arm, False to disarm.
    """
    logger.info(f"Tool call: arm_disarm(arm={arm})")
    conn = connect()
    result = send_cmd(conn, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1 if arm else 0)
    if result == "accepted":
        logger.info(f"Pixhawk is {'armed' if arm else 'disarmed'}")
        return "armed" if arm else "disarmed"
    return f"command {result}"


@mcp.tool()
@tool_guard
def set_mode(mode: str) -> str:
    """
    Set the flight mode.

    Args:
        mode: Mode name, e.g. GUIDED, LOITER, RTL, LAND, STABILIZE, ALT_HOLD.
    """
    logger.info(f"Tool call: set_mode(mode={mode})")
    conn = connect()
    mode_id = conn.mode_mapping().get(mode.upper())
    if mode_id is None:
        logger.warning(f"Unknown mode requested: {mode}")
        return f"unknown mode '{mode}'"
    conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)
    ack = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=config.CMD_ACK_TIMEOUT_S)
    if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        logger.info(f"Mode set to {mode.upper()}")
        return f"mode set to {mode.upper()}"
    result = ack.result if ack else "timeout"
    logger.warning(f"Mode change to {mode.upper()} failed: {result}")
    return f"mode change {result}"


@mcp.tool()
@tool_guard
def goto(lat: float, lon: float, altitude_m: float) -> str:
    """
    Fly to a GPS coordinate at the given altitude (requires GUIDED mode).

    If the caller hasn't provided a target lat/lon, call get_gps_position
    first to read the drone's current position (e.g. to hold in place at a
    new altitude, or to compute a position relative to where it already is)
    rather than guessing coordinates.

    Args:
        lat: Target latitude in decimal degrees.
        lon: Target longitude in decimal degrees.
        altitude_m: Target altitude above home in metres.
    """
    logger.info(f"Tool call: goto(lat={lat}, lon={lon}, altitude_m={altitude_m})")
    conn = connect()
    conn.mav.send(mavutil.mavlink.MAVLink_set_position_target_global_int_message(
        0,
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000,  # position only
        int(lat * 1e7), int(lon * 1e7), altitude_m,
        0, 0, 0, 0, 0, 0, 0, 0,
    ))
    logger.info(f"heading to ({lat}, {lon}) at {altitude_m} m")
    return f"heading to ({lat}, {lon}) at {altitude_m} m"


@mcp.tool()
@tool_guard
def land() -> str:
    """Command the drone to land at the current position."""
    logger.info("Tool call: land")
    conn = connect()
    result = send_cmd(conn, mavutil.mavlink.MAV_CMD_NAV_LAND)
    logger.info(f"Land command {result}")
    return f"land command {result}"
