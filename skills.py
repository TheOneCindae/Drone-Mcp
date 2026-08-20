"""Composite, multi-step drone behaviors built on top of the primitives in
tools.py/mavlink_client.py (arm, set mode, send a command, wait for altitude)."""

import logging
import time

from pymavlink import mavutil

from app import mcp
from mavlink_client import connect, send_cmd, tool_guard, wait_for_alt

logger = logging.getLogger("pixhawk-mcp")


@mcp.tool()
@tool_guard
def takeoff_and_hover(target_altitude_m: float = 5.0) -> str:
    """
    Arm the drone, switch to GUIDED mode, take off to target altitude, and hover.

    Args:
        target_altitude_m: Desired hover altitude in metres (default 5 m).
    """
    logger.info(f"Tool call: takeoff_and_hover(target_altitude_m={target_altitude_m})")
    conn = connect()

    # 1. Set GUIDED mode
    logger.debug("Setting GUIDED mode")
    conn.mav.set_mode_send(
        conn.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        4,  # GUIDED mode number for ArduPilot
    )
    time.sleep(1)

    # 2. Arm
    logger.debug("Arming")
    send_cmd(conn, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    time.sleep(2)

    # 3. Takeoff
    logger.debug(f"Sending takeoff command to {target_altitude_m} m")
    send_cmd(conn, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, target_altitude_m)

    # 4. Wait until target altitude is reached (±0.5 m)
    msg, reached = wait_for_alt(conn, target_altitude_m)
    if reached:
        logger.info(f"hovering at {target_altitude_m} m")
        return f"hovering at {target_altitude_m} m"
    result = f"takeoff timeout — last alt {msg.relative_alt / 1000:.1f} m" if msg else "no position data"
    logger.warning(result)
    return result


@mcp.tool()
@tool_guard
def return_to_launch() -> str:
    """Switch to RTL mode and wait for the drone to land at the home position."""
    logger.info("Tool call: return_to_launch")
    conn = connect()
    mode_id = conn.mode_mapping().get("RTL")
    if mode_id is None:
        logger.warning("RTL mode not available")
        return "RTL mode not available"
    conn.mav.set_mode_send(conn.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)
    # Wait until altitude drops to near zero (landed)
    msg, landed = wait_for_alt(conn, 0.0, tolerance=1.0, timeout=60)
    if landed:
        logger.info("landed at home")
        return "landed at home"
    result = f"RTL timeout — last alt {msg.relative_alt / 1000:.1f} m" if msg else "no position data"
    logger.warning(result)
    return result
