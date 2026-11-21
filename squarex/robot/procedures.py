"""What the CLI asks the robot to do, as sequences of ROS calls."""
import subprocess
import time
from collections.abc import Callable

from squarex import runtime
from squarex.config import (MOTOR_DRIVER_CONTAINER, READY_TOLERANCE_DEG, READY_TOLERANCE_MM, SSH_KEY,
                            SSH_KNOWN_HOSTS, Settings)
from squarex.robot import ready_pose
from squarex.robot.ros import (TOPICS, ControllerMode, Inference, InferenceCommand, Planner, Safety, control_inference,
                               model_info, read_status, switch_controller_mode)
from squarex.robot.rosbridge import RosBridge

Say = Callable[[str], None]
IDLE_INFERENCE = (Inference.UNINITIALIZED, Inference.CLOSED)


class NotReady(RuntimeError):
    pass


def connect(settings: Settings) -> RosBridge:
    return RosBridge(settings.rosbridge_url, TOPICS)


def _require_idle_and_healthy(bridge: RosBridge) -> None:
    status = read_status(bridge)
    if not status.healthy:
        raise NotReady(f"robot not healthy: {status.safety!r} {status.safety_message}")
    if not status.idle:
        raise NotReady(f"robot busy: inference {status.inference!r}, controller {status.controller_mode!r}")


def _begin_inference(bridge: RosBridge, settings: Settings, prompt: str, say: Say) -> None:
    say("INIT_MODEL -> model at " + settings.gateway_url)
    control_inference(bridge, InferenceCommand.INIT_MODEL, model_info(prompt, settings.gateway_url), timeout=75)
    bridge.wait_until(lambda: read_status(bridge).inference == Inference.INITIALIZED, 70, "model initialized")
    say("controller mode -> POSE_INFERENCE")
    switch_controller_mode(bridge, ControllerMode.POSE_INFERENCE)
    bridge.wait_until(lambda: (s := read_status(bridge)).controller_mode == ControllerMode.POSE_INFERENCE and s.controller_ready,
                      10, "pose inference mode")
    say("START")
    control_inference(bridge, InferenceCommand.START)
    bridge.wait_until(lambda: read_status(bridge).inference == Inference.INFERRING, 65, "inference running")


def _end_inference(bridge: RosBridge, say: Say) -> None:
    if read_status(bridge).inference not in IDLE_INFERENCE:
        say("STOP, CLOSE")
        control_inference(bridge, InferenceCommand.STOP)
        control_inference(bridge, InferenceCommand.CLOSE)
        bridge.wait_until(lambda: read_status(bridge).inference in IDLE_INFERENCE, 15, "inference closed")
    if read_status(bridge).controller_mode not in (ControllerMode.UNSELECTED, ControllerMode.IDLE):
        say("controller mode -> IDLE")
        switch_controller_mode(bridge, ControllerMode.IDLE)


def _move_to_ready_pose(bridge: RosBridge, settings: Settings, say: Say) -> None:
    say("moving to the ready pose")
    runtime.set_mode(runtime.READY)
    try:
        _begin_inference(bridge, settings, "move to the ready pose", say)
        bridge.wait_until(lambda: ready_pose.reached(read_status(bridge).arms, READY_TOLERANCE_MM, READY_TOLERANCE_DEG),
                          30, "ready pose")
        say("ready pose reached")
    finally:
        _end_inference(bridge, say)
        runtime.set_mode(runtime.INFERENCE)


def _supervise(bridge: RosBridge, seconds: int, say: Say) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        bridge.listen(0.5)
        status = read_status(bridge)
        if status.inference != Inference.INFERRING:
            say(f"inference ended: {status.inference!r}")
            return
        if not status.healthy:
            say(f"robot fault: {status.safety!r} {status.safety_message}")
            return
    say(f"time limit of {seconds} s reached")


def start(settings: Settings, model: str, prompt: str, seconds: int, use_ready_pose: bool, say: Say) -> None:
    with connect(settings) as bridge:
        _require_idle_and_healthy(bridge)
        say(f"run {runtime.new_run()} with the {model} model: {prompt!r}, at most {seconds} s")
        runtime.set_model(model)
        runtime.set_prompt(prompt)
        if use_ready_pose:
            _move_to_ready_pose(bridge, settings, say)
        try:
            _begin_inference(bridge, settings, prompt, say)
            say("running")
            _supervise(bridge, seconds, say)
        finally:
            _end_inference(bridge, say)
    say("done")


def stop(settings: Settings, say: Say) -> None:
    with connect(settings) as bridge:
        _end_inference(bridge, say)
    say("stopped")


def _at_home(arms: dict[str, list[float]], tolerance_mm: float = 15) -> bool:
    return all(sum(v * v for v in pose[:3]) ** 0.5 * 1000 <= tolerance_mm for pose in arms.values())


def home(settings: Settings, say: Say) -> None:
    with connect(settings) as bridge:
        _require_idle_and_healthy(bridge)
        say("controller mode -> ROBOT_HOMING")
        switch_controller_mode(bridge, ControllerMode.ROBOT_HOMING)
        try:
            bridge.wait_until(lambda: read_status(bridge).controller_mode == ControllerMode.ROBOT_HOMING, 5, "homing mode")
            bridge.wait_until(lambda: (s := read_status(bridge)).planner == Planner.RUNNING or _at_home(s.arms), 5, "homing started")
            bridge.wait_until(lambda: read_status(bridge).planner in (Planner.FINISHED, Planner.ERROR), 45, "homing finished")
            say(f"homing {read_status(bridge).planner!r}")
        finally:
            switch_controller_mode(bridge, ControllerMode.IDLE)
            say("controller mode -> IDLE")


def _ssh(settings: Settings, command: str, timeout: int) -> str:
    result = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", f"UserKnownHostsFile={SSH_KNOWN_HOSTS}", "-o", "BatchMode=yes",
         "-o", "ConnectTimeout=5", settings.robot_ssh, command],
        capture_output=True, text=True, timeout=timeout, check=True)
    return result.stdout.strip()


def clear_bus_error(settings: Settings, say: Say) -> None:
    """The CAN adapters dropped out and came back, but the motor driver still holds the old buses: restart it."""
    with connect(settings) as bridge:
        if not read_status(bridge).motors_disconnected:
            raise NotReady("no bus error reported")
        interfaces, adapters = _ssh(settings, "ip -br link | grep -cE '^can[1-4] +UP'; lsusb | grep -c 'PCAN-USB Pro FD'", 15).split()
        say(f"CAN interfaces up: {interfaces}/4, PEAK adapters: {adapters}/2")
        if (int(interfaces), int(adapters)) != (4, 2):
            raise NotReady("CAN adapters missing: check their USB cables and power, a restart will not help")
        say(f"restarting {MOTOR_DRIVER_CONTAINER}")
        _ssh(settings, f"docker restart -t 20 {MOTOR_DRIVER_CONTAINER}", 60)
        bridge.wait_until(lambda: read_status(bridge).safety == Safety.NO_ERROR, 60, "bus recovered")
    say("bus recovered")
