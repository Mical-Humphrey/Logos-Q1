from __future__ import annotations

import socket

import pytest

import conftest  # pytest loads tests/conftest.py as top-level module


def test_socket_guard_blocks_outbound_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guard fixture should already be active; creating a socket should succeed
    # but attempting to connect must raise our custom error.
    sock = socket.socket()
    try:
        sock.connect(("example.com", 80))
    except conftest.NetworkAccessError:
        pass
    else:
        pytest.fail("Socket guard did not block connect")
    try:
        sock.connect_ex(("example.com", 443))
    except OSError:
        pass
    else:
        pytest.fail("Socket guard did not block connect_ex")


def test_socket_guard_blocks_create_connection() -> None:
    try:
        socket.create_connection(("example.com", 80))
    except conftest.NetworkAccessError:
        pass
    else:
        pytest.fail("Socket guard did not block create_connection")
