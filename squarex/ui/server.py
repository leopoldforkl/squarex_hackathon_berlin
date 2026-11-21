"""A web page that only runs CLI commands and shows their output."""
import json
import shlex
import subprocess
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from squarex.config import Settings

PAGE = Path(__file__).with_name("index.html").read_bytes()
ALLOWED_COMMANDS = {"start", "stop", "home", "prompt", "clear-bus-error"}


def cli(args: list[str]) -> list[str]:
    return [sys.executable, "-m", "squarex", *args]


class Job:
    def __init__(self, args: list[str]):
        self.command_line = shlex.join(["squarex", *args])
        self.output: list[str] = []
        self.process = subprocess.Popen(cli(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        threading.Thread(target=self._collect, daemon=True).start()

    def _collect(self) -> None:
        for line in self.process.stdout:
            self.output.append(line.rstrip())

    def to_json(self) -> dict:
        return {"command": self.command_line, "output": self.output, "running": self.process.poll() is None,
                "exit_code": self.process.poll()}


jobs: deque[Job] = deque(maxlen=20)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._reply(200, PAGE, "text/html")
        elif self.path == "/api/status":
            result = subprocess.run(cli(["status", "--json"]), capture_output=True, text=True, timeout=20)
            body = result.stdout if result.returncode == 0 else json.dumps({"error": result.stderr.strip()})
            self._reply(200, body.encode(), "application/json")
        elif self.path == "/api/jobs":
            self._reply(200, json.dumps([job.to_json() for job in reversed(jobs)]).encode(), "application/json")
        else:
            self._reply(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/run" or self.headers.get("Content-Type") != "application/json":
            return self._reply(400, b"bad request", "text/plain")
        args = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["args"]
        if not args or args[0] not in ALLOWED_COMMANDS:
            return self._reply(403, b"command not allowed", "text/plain")
        jobs.append(Job([str(arg) for arg in args]))
        self._reply(200, json.dumps(jobs[-1].to_json()).encode(), "application/json")

    def _reply(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def run(settings: Settings) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", settings.ui_port), Handler)
    print(f"ui on http://127.0.0.1:{settings.ui_port}", flush=True)
    server.serve_forever()
