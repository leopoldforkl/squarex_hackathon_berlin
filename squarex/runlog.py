"""Every message of a run as one JSON line; images are stored next to it and referenced by file name."""
import json
import time

from squarex.arrays import to_list
from squarex.config import LOG_DIR


def jsonable(value):
    """Make a decoded msgpack message printable as JSON: arrays become lists, raw bytes become their size."""
    if isinstance(value, dict):
        if value.get("nd", value.get(b"nd")) is True:
            return to_list(value)
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    return value


class RunLog:
    def __init__(self, run_id: str, stream: str):
        self.dir = LOG_DIR / run_id
        (self.dir / "images").mkdir(parents=True, exist_ok=True)
        self._file = (self.dir / f"{stream}.jsonl").open("a")

    def write(self, step: int, direction: str, message) -> None:
        line = {"time": time.strftime("%H:%M:%S"), "step": step, "direction": direction, "message": jsonable(message)}
        self._file.write(json.dumps(line) + "\n")
        self._file.flush()

    def save_image(self, step: int, view: str, jpeg: bytes) -> str:
        name = f"images/{step:03d}-{view}.jpg"
        (self.dir / name).write_bytes(jpeg)
        return name

    def close(self) -> None:
        self._file.close()


def log_ros(entry: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / "ros.jsonl").open("a") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **entry}) + "\n")
