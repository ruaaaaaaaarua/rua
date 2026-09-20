"""Backend regressions must use mock transports, never live providers."""
import socket

import pytest


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('Backend tests require an in-process/mock transport')
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('Backend tests require an in-process/mock transport')
        return original_connect_ex(sock, address)

    def resolve(*args, **kwargs):
        raise AssertionError('Backend tests must not perform DNS lookups')

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex)
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
