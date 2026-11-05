"""Coordination backends (ADR-0001).

whatsnext reports what happens (an event and a dict payload) to one backend.
Another backend is added without changing whatsnext: set `backend.name` to
an import path such as "package.module:ClassName".
"""

import importlib

EVENTS = (
    "session.start",
    "task.start",
    "task.release",
    "task.done",
    "status.write",
    "decision.capture",
    "session.wrapup",
)


class BackendError(ValueError):
    """A backend name cannot be resolved."""


class Backend(object):
    """Base class. Subclasses set `name` and implement `deliver`."""

    name = ""

    def emit(self, event, payload):
        """Validate, then hand the event to the backend. Same checks for all."""
        if event not in EVENTS:
            raise ValueError("unknown event %r (expected one of: %s)" % (event, ", ".join(EVENTS)))
        if not isinstance(payload, dict):
            raise ValueError("payload for %s must be a dict (got %s)" % (event, type(payload).__name__))
        self.deliver(event, payload)

    def deliver(self, event, payload):
        raise NotImplementedError


class LocalFilesBackend(Backend):
    """Default backend: reads and writes only files in the repository.

    For now it only validates events. Feature code writes the files in later steps.
    """

    name = "local-files"

    def deliver(self, event, payload):
        return None


class FakeBackend(Backend):
    """Test double: records (event, payload) pairs in `events`."""

    name = "fake"

    def __init__(self):
        self.events = []

    def deliver(self, event, payload):
        self.events.append((event, payload))


_REGISTRY = {}


def register_backend(name, cls):
    _REGISTRY[name] = cls


register_backend(LocalFilesBackend.name, LocalFilesBackend)


def _import_backend(path):
    module_name, _, class_name = path.partition(":")
    try:
        cls = getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise BackendError("cannot load backend %r: %s" % (path, e))
    return cls


def get_backend(effective_or_name):
    """Return a backend instance from an Effective config or a backend name."""
    if isinstance(effective_or_name, str):
        name = effective_or_name
    else:
        name = effective_or_name.get("backend.name")
    if name in _REGISTRY:
        cls = _REGISTRY[name]
    elif ":" in name:
        cls = _import_backend(name)
    else:
        raise BackendError("unknown backend %r (registered: %s; or use \"package.module:ClassName\")"
                           % (name, ", ".join(sorted(_REGISTRY))))
    if not (isinstance(cls, type) and issubclass(cls, Backend)):
        raise BackendError("backend %r is not a subclass of wn.backend.Backend" % name)
    return cls()
