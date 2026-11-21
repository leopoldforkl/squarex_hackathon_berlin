"""rosbridge speaks JSON over a WebSocket. Service calls are logged to logs/ros.jsonl."""
import itertools
import json
import time
from collections.abc import Callable

from websockets.sync.client import connect

from squarex.runlog import log_ros


class RosError(RuntimeError):
    pass


class RosBridge:
    def __init__(self, url: str, topics: dict[str, str]):
        self._ws = connect(url, max_size=None, open_timeout=5)
        self._ids = itertools.count()
        self.latest: dict[str, dict] = {}
        for topic, message_type in topics.items():
            self._send({"op": "subscribe", "topic": topic, "type": message_type, "throttle_rate": 100, "queue_length": 1})
        self.wait_until(lambda: all(topic in self.latest for topic in topics), timeout=5, what="first messages of all topics")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._ws.close()

    def call(self, service: str, request: dict, timeout: float = 10) -> dict:
        call_id = f"call-{next(self._ids)}"
        self._send({"op": "call_service", "id": call_id, "service": service, "args": request})
        deadline = time.monotonic() + timeout
        while (reply := self._receive(deadline, service))["op"] != "service_response" or reply["id"] != call_id:
            pass
        log_ros({"service": service, "request": request, "ok": reply["result"], "response": reply.get("values")})
        if not reply["result"]:
            raise RosError(f"{service} failed: {reply.get('values')}")
        return reply.get("values") or {}

    def wait_until(self, condition: Callable[[], bool], timeout: float, what: str) -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            self._receive(deadline, what)

    def listen(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        try:
            while True:
                self._receive(deadline, "updates")
        except TimeoutError:
            pass

    def _send(self, message: dict) -> None:
        self._ws.send(json.dumps(message))

    def _receive(self, deadline: float, what: str) -> dict:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for {what}")
        try:
            message = json.loads(self._ws.recv(timeout=remaining))
        except TimeoutError:
            raise TimeoutError(f"timed out waiting for {what}") from None
        if message.get("op") == "publish":
            self.latest[message["topic"]] = message["msg"]
        return message
