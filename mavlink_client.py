"""
MAVLink connection lifecycle: a single shared connection reused across tool
calls, with retry/backoff on (re)connection, plus small helpers tools.py and
skills.py build on (_send_cmd, wait_for_alt) and the error-handling decorator
every tool is wrapped in.
"""

import functools
import logging
import threading
import time

from pymavlink import mavutil

import config

logger = logging.getLogger("pixhawk-mcp")

_conn: mavutil.mavfile | None = None
_conn_lock = threading.Lock()


def _open_connection() -> mavutil.mavfile:
    """Open a fresh MAVLink connection and block until a heartbeat is seen."""
    logger.info(f"Opening MAVLink connection on {config.MAVLINK_ENDPOINT} ...")
    conn = mavutil.mavlink_connection(config.MAVLINK_ENDPOINT)

    logger.debug(f"Socket bound, waiting up to {config.HEARTBEAT_TIMEOUT_S}s for heartbeat ...")
    hb = conn.wait_heartbeat(timeout=config.HEARTBEAT_TIMEOUT_S)
    if hb is None:
        conn.close()
        logger.error(
            f"No heartbeat received within {config.HEARTBEAT_TIMEOUT_S}s. "
            f"Is the simulator/vehicle running and sending MAVLink to {config.MAVLINK_ENDPOINT}?"
        )
        raise ConnectionError(f"Timed out waiting for heartbeat on {config.MAVLINK_ENDPOINT}")

    logger.info(f"Heartbeat received — connected (system {conn.target_system}, component {conn.target_component})")
    return conn


def close_connection() -> None:
    global _conn
    with _conn_lock:
        if _conn is not None:
            logger.info("Closing MAVLink connection")
            try:
                _conn.close()
            except Exception as e:
                logger.debug(f"Error closing connection (ignored): {e}")
            _conn = None


def connect() -> mavutil.mavfile:
    """
    Return a live, shared MAVLink connection, reused across tool calls, with
    retry/backoff on (re)connection. A brand-new connection per tool call
    previously left multiple sockets bound to the same UDP port racing each
    other for packets; this keeps a single connection alive per process and
    only reconnects if it's actually gone stale.
    """
    global _conn

    with _conn_lock:
        if _conn is not None:
            logger.debug("Reusing existing MAVLink connection, checking staleness ...")
            hb = _conn.recv_match(type="HEARTBEAT", blocking=True, timeout=config.HEARTBEAT_TIMEOUT_S)
            if hb is not None:
                logger.debug("Existing connection is alive.")
                return _conn
            logger.warning("Existing connection went stale (no heartbeat) — reconnecting.")
            try:
                _conn.close()
            except Exception as e:
                logger.debug(f"Error closing stale connection (ignored): {e}")
            _conn = None

        last_err: Exception | None = None
        for attempt in range(1, config.RECONNECT_MAX_RETRIES + 1):
            try:
                _conn = _open_connection()
                return _conn
            except Exception as e:
                last_err = e
                logger.warning(f"Connect attempt {attempt}/{config.RECONNECT_MAX_RETRIES} failed: {e}")
                if attempt < config.RECONNECT_MAX_RETRIES:
                    time.sleep(config.RECONNECT_BACKOFF_S * attempt)

        logger.error(f"Failed to connect to Pixhawk after {config.RECONNECT_MAX_RETRIES} attempts: {last_err}")
        raise ConnectionError(
            f"Failed to connect to Pixhawk after {config.RECONNECT_MAX_RETRIES} attempts: {last_err}"
        )


def tool_guard(fn):
    """Turn unexpected exceptions into a clean string result instead of a raw
    traceback bubbling up through the MCP protocol, and log every failure."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ConnectionError as e:
            logger.error(f"{fn.__name__} failed: {e}")
            return f"error: {e}"
        except Exception:
            logger.exception(f"{fn.__name__} failed unexpectedly")
            return f"error: {fn.__name__} failed unexpectedly, see {config.LOG_FILE.name}"

    return wrapper


def send_cmd(conn: mavutil.mavfile, cmd: int, *params) -> str:
    p = list(params) + [0] * (7 - len(params))
    logger.debug(f"Sending command_long: cmd={cmd} params={p[:7]}")
    conn.mav.command_long_send(conn.target_system, conn.target_component, cmd, 0, *p[:7])
    ack = conn.recv_match(type="COMMAND_ACK", blocking=True, timeout=config.CMD_ACK_TIMEOUT_S)
    if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        logger.debug(f"Command {cmd} accepted")
        return "accepted"
    result = ack.result if ack else "timeout"
    logger.warning(f"Command {cmd} rejected/timed out: result={result}")
    return f"rejected (result={result})"


def wait_for_alt(conn: mavutil.mavfile, target_m: float, tolerance: float = 0.5, timeout: float = 30):
    deadline = time.time() + timeout
    msg = None
    while time.time() < deadline:
        msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
        if msg:
            logger.debug(f"Current alt: {msg.relative_alt / 1000:.2f} m (target {target_m} m)")
        if msg and abs(msg.relative_alt / 1000 - target_m) < tolerance:
            return msg, True
    logger.warning(f"Timed out waiting for altitude {target_m} m (tolerance {tolerance} m)")
    return msg, False
