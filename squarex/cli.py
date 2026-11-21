import argparse
import json
import sys

from squarex import gateway, runtime
from squarex.config import load_settings
from squarex.models import MODELS
from squarex.robot import procedures
from squarex.robot.ros import read_status


def say(line: str) -> None:
    print(line, flush=True)


def status(settings, args) -> None:
    with procedures.connect(settings) as bridge:
        report = read_status(bridge).to_json() | {"model": runtime.model(), "prompt": runtime.prompt(), "run": runtime.run_id()}
    if args.json:
        print(json.dumps(report))
        return
    for key, value in report.items():
        print(f"{key:18} {value}")


def start(settings, args) -> None:
    procedures.start(settings, args.model, args.prompt, args.seconds, use_ready_pose=not args.no_ready_pose, say=say)


def stop(settings, args) -> None:
    procedures.stop(settings, say)


def home(settings, args) -> None:
    procedures.home(settings, say)


def prompt(settings, args) -> None:
    runtime.set_prompt(args.text)
    say(f"prompt for the next model step: {args.text!r}")


def clear_bus_error(settings, args) -> None:
    procedures.clear_bus_error(settings, say)


def run_gateway(settings, args) -> None:
    gateway.run(settings)


def run_ui(settings, args) -> None:
    from squarex.ui.server import run
    run(settings)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="squarex", description="Run the squarex robot with the WALLX cloud model or a local model.")
    commands = cli.add_subparsers(dest="command", required=True)

    commands.add_parser("status", help="robot state").add_argument("--json", action="store_true")
    start_cmd = commands.add_parser("start", help="run the model with a prompt")
    start_cmd.add_argument("prompt")
    start_cmd.add_argument("--model", choices=sorted(MODELS), default="cloud", help="default: cloud")
    start_cmd.add_argument("--seconds", type=int, default=90, help="time limit (default 90)")
    start_cmd.add_argument("--no-ready-pose", action="store_true", help="start from where the arms are")
    commands.add_parser("stop", help="stop the running inference")
    commands.add_parser("home", help="move both arms to the home pose")
    commands.add_parser("prompt", help="change the prompt of the running inference").add_argument("text")
    commands.add_parser("clear-bus-error", help="restart the motor driver after the CAN adapters dropped out")
    commands.add_parser("gateway", help="serve the model connection for the robot client")
    commands.add_parser("ui", help="web page that runs these commands")
    return cli


COMMANDS = {
    "status": status, "start": start, "stop": stop, "home": home, "prompt": prompt,
    "clear-bus-error": clear_bus_error, "gateway": run_gateway, "ui": run_ui,
}


def main() -> None:
    args = parser().parse_args()
    try:
        COMMANDS[args.command](load_settings(), args)
    except Exception as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
