"""WebSocket client for the WALLX cloud model (msgpack messages)."""
import msgpack
from websockets.sync.client import connect

from squarex.config import Settings


class WallxError(RuntimeError):
    pass


class Wallx:
    def __init__(self, settings: Settings):
        self._ws = connect(settings.wallx_url, additional_headers={"Authorization": f"Bearer {settings.wallx_api_key}"},
                           max_size=None, open_timeout=20, ping_interval=None)
        self.metadata_raw = self._ws.recv(timeout=60)
        self.metadata = msgpack.unpackb(self.metadata_raw, raw=False, strict_map_key=False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._ws.close()

    def infer(self, request: dict) -> dict:
        self._ws.send(msgpack.packb(request, use_bin_type=True))
        reply = msgpack.unpackb(self._ws.recv(timeout=60), raw=False, strict_map_key=False)
        if "error" in reply:
            raise WallxError(reply["error"])
        return reply
