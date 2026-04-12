"""
Signals can only be registered in the main thread and there can only be a
single wakeup FD. As a consequence, `subscribe_signals()` should only be used
once, early on in the application.
"""

import contextlib
import signal
import socket
from collections.abc import AsyncGenerator
from collections.abc import Generator


def noop(*args):
    pass


@contextlib.contextmanager
def signal_fd() -> Generator[int, None, None]:
    r, w = socket.socketpair()
    r.setblocking(False)  # noqa
    w.setblocking(False)  # noqa

    old = signal.set_wakeup_fd(w.fileno())
    try:
        yield r.fileno()
    finally:
        signal.set_wakeup_fd(old)
        r.close()
        w.close()


@contextlib.asynccontextmanager
async def subscribe_signals(*sigs: int) -> AsyncGenerator[int, None]:
    with signal_fd() as fd:
        old_sigs = {sig: signal.signal(sig, noop) for sig in sigs}
        try:
            yield fd
        finally:
            for sig, old in old_sigs.items():
                signal.signal(sig, old)
