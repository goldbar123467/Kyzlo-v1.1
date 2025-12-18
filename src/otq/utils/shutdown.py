from __future__ import annotations

import signal
import threading

_STOP_EVENT = threading.Event()


def request_stop() -> None:
    _STOP_EVENT.set()


def stopping() -> bool:
    return _STOP_EVENT.is_set()


def install_signal_handlers() -> None:
    # Safe on Windows + Linux
    def _handler(signum, frame):  # pragma: no cover
        request_stop()

        # Preserve default Ctrl+C behavior (KeyboardInterrupt) so existing
        # try/except/finally shutdown paths still run.
        if signum == signal.SIGINT:
            try:
                signal.default_int_handler(signum, frame)
            except Exception:
                pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass
