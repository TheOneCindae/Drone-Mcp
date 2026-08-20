"""
Single-instance guard.

Multiple server processes binding the same MAVLink endpoint at once is what
caused unreliable connections before (packets split unpredictably between
their sockets). acquire() refuses to start a second instance rather than
silently repeating that bug, and reports the holding PID so it's easy to
find and stop.
"""

import logging
import os
import sys

import config

logger = logging.getLogger("pixhawk-mcp")

_lock_fh = None


def acquire() -> None:
    # Opened as "r+" (not append) because msvcrt.locking() locks a byte range
    # at the file's current seek position, and append mode forces every write
    # to the actual end of file regardless of seek — the mismatch between
    # where the lock sits and where writes land makes Windows reject the
    # write with a PermissionError instead of the lock ever visibly failing.
    global _lock_fh
    if not config.LOCK_FILE.exists():
        config.LOCK_FILE.touch()
    _lock_fh = open(config.LOCK_FILE, "r+")
    try:
        if os.name == "nt":
            import msvcrt
            _lock_fh.seek(0)
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            _lock_fh.seek(0)
            holder_pid = _lock_fh.read().strip() or "unknown"
        except OSError:
            holder_pid = "unknown"
        _lock_fh.close()
        _lock_fh = None
        logger.critical(
            f"Another pixhawk-mcp instance (pid {holder_pid}) is already running "
            f"(lock: {config.LOCK_FILE}). Refusing to start a second instance — see "
            f"module docstring for why. To force it closed: "
            f"Stop-Process -Id {holder_pid} -Force"
        )
        sys.exit(1)
    _lock_fh.seek(0)
    _lock_fh.write(str(os.getpid()))
    _lock_fh.truncate()
    _lock_fh.flush()
    logger.debug(f"Acquired single-instance lock (pid {os.getpid()})")


def release() -> None:
    if _lock_fh is None or _lock_fh.closed:
        return
    try:
        if os.name == "nt":
            import msvcrt
            _lock_fh.seek(0)
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_UN)
        _lock_fh.close()
    except OSError:
        pass
