"""State shared between CLI commands and the gateway, kept as small files in runtime/."""
import time

from squarex.config import RUNTIME_DIR

READY = "ready"
INFERENCE = "inference"


def _write(name: str, value: str) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    (RUNTIME_DIR / name).write_text(value)


def _read(name: str, default: str) -> str:
    path = RUNTIME_DIR / name
    return path.read_text() if path.exists() else default


def set_prompt(prompt: str) -> None:
    _write("prompt", prompt)


def prompt() -> str:
    return _read("prompt", "")


def set_model(model: str) -> None:
    _write("model", model)


def model() -> str:
    return _read("model", "cloud")


def set_mode(mode: str) -> None:
    _write("mode", mode)


def mode() -> str:
    return _read("mode", INFERENCE)


def new_run() -> str:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    _write("run", run_id)
    return run_id


def run_id() -> str:
    return _read("run", "no-run")
