"""A model server speaks msgpack over a WebSocket: metadata on connect, then one reply per request."""
import msgpack
from websockets.sync.client import connect


class ModelError(RuntimeError):
    pass


class ModelSocket:
    def __init__(self, url: str, headers: dict | None = None):
        self._ws = connect(url, additional_headers=headers, max_size=None, open_timeout=20, ping_interval=None)
        self.metadata_raw = self._ws.recv(timeout=60)
        self.metadata = msgpack.unpackb(self.metadata_raw, raw=False, strict_map_key=False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._ws.close()

    def exchange(self, request: dict) -> dict:
        self._ws.send(msgpack.packb(request, use_bin_type=True))
        raw = self._ws.recv(timeout=60)
        if isinstance(raw, str):
            raise ModelError(raw[-500:])
        reply = msgpack.unpackb(raw, raw=False, strict_map_key=False)
        if "error" in reply:
            raise ModelError(reply["error"])
        return reply
