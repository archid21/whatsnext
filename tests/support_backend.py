"""A tiny backend loaded by import path in tests: "support_backend:TinyBackend"."""

from wn.backend import Backend


class TinyBackend(Backend):
    name = "tiny"

    def deliver(self, event, payload):
        pass


class NotABackend(object):
    pass


class LogBackend(Backend):
    """Appends each event as a JSON line to the file named by $GW_TEST_EVENTS."""

    name = "log"

    def deliver(self, event, payload):
        import json
        import os

        with open(os.environ["GW_TEST_EVENTS"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": event, "payload": payload}) + "\n")
