"""Hooks a lower app reads and a higher app fills in at startup, so imports only point one way."""

_registry = {}


def register(name, fn):
    _registry[name] = fn


def get(name):
    return _registry.get(name)
