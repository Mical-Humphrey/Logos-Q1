import os
import socket
import sys
from pathlib import Path
from typing import Generator

import pytest

# Ensure the project root is on sys.path so `import logos` works in tests.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class NetworkAccessError(RuntimeError):
    """Raised when a test attempts to open an outbound socket."""


@pytest.fixture(scope="session", autouse=True)
def _block_outbound_sockets() -> Generator[None, None, None]:
    """Guard the test suite against unintended outbound network calls."""

    os.environ.setdefault("LIVE_DISABLE_NETWORK", "1")

    original_socket = socket.socket
    original_create_connection = socket.create_connection

    class GuardedSocket(socket.socket):
        def connect(self, address):  # type: ignore[override]
            raise NetworkAccessError(
                f"Outbound network disabled during tests: attempted connect to {address}"
            )

        def connect_ex(self, address):  # type: ignore[override]
            raise OSError(
                f"Outbound network disabled during tests: attempted connect to {address}"
            )

    def guarded_create_connection(*args: object, **kwargs: object) -> socket.socket:  # type: ignore[override]
        raise NetworkAccessError(
            f"Outbound network disabled during tests: attempted create_connection to {args[0]}"
        )

    setattr(socket, "socket", GuardedSocket)
    setattr(socket, "create_connection", guarded_create_connection)
    try:
        yield
    finally:
        setattr(socket, "socket", original_socket)
        setattr(socket, "create_connection", original_create_connection)
