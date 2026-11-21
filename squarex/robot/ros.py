"""The robot's ROS interfaces and their translation to plain Python values."""
import json
import math
from dataclasses import dataclass
from enum import IntEnum

from squarex.config import INFER_PARAMS
from squarex.robot.rosbridge import RosBridge, RosError

INFERENCE_CONTROL = "/x2robot_infer/inference_control"
SWITCH_CONTROLLER_MODE = "/realtime_controller_manager/switch_controller_mode"

INFERENCE_STATUS = "/x2robot_infer/inference_status"
CONTROLLER_STATUS = "/realtime_controller_manager/mode_controller_enabled_status"
SAFETY_STATE = "/robot_state"
ARM_POSES = {"left": "/left_arm/end_pose", "right": "/right_arm/end_pose"}
GRIPPERS = {"left": "/left_gripper/joint_states", "right": "/right_gripper/joint_states"}

TOPICS = {
    INFERENCE_STATUS: "protocol/msg/InferenceStatus",
    CONTROLLER_STATUS: "protocol/msg/ModeControllerEnabledStatus",
    SAFETY_STATE: "x2robot_msgs/msg/RobotArmState",
    **{topic: "geometry_msgs/msg/PoseStamped" for topic in ARM_POSES.values()},
    **{topic: "sensor_msgs/msg/JointState" for topic in GRIPPERS.values()},
}


class InferenceCommand(IntEnum):
    INIT_MODEL = 1
    START = 2
    STOP = 3
    CLOSE = 4
    UPDATE_INSTRUCTION = 5


class Inference(IntEnum):
    UNINITIALIZED = 0
    INITIALIZING = 1
    INITIALIZED = 2
    INFERRING = 3
    STOPPING = 4
    CLOSED = 5
    TAKEOVER_NEEDED = 6
    RESUMING = 7
    ERROR = 255


class ControllerMode(IntEnum):
    UNSELECTED = 0
    IDLE = 1
    JOINT_INFERENCE = 4
    POSE_INFERENCE = 6
    ROBOT_HOMING = 9


class Planner(IntEnum):
    UNKNOWN = 0
    IDLE = 1
    RUNNING = 2
    FINISHED = 3
    ERROR = 4


class Safety(IntEnum):
    NO_ERROR = 0
    READY = 1
    EMERGENCY_STOPPED = 2
    POWER_OFF = 3
    NOT_ENABLED = 4
    MOTOR_ERROR = 5
    BUS_ERROR = 6


def _named(enum: type[IntEnum], value: int) -> IntEnum | int:
    try:
        return enum(value)
    except ValueError:
        return value


def _rpy(q: dict) -> list[float]:
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return [roll, pitch, yaw]


def arm_pose(pose_stamped: dict, gripper_state: dict) -> list[float]:
    """PoseStamped + gripper JointState -> [x, y, z, roll, pitch, yaw, gripper] (the robot client's arm format)."""
    position = pose_stamped["pose"]["position"]
    return [position["x"], position["y"], position["z"], *_rpy(pose_stamped["pose"]["orientation"]), gripper_state["position"][0]]


@dataclass
class RobotStatus:
    inference: Inference | int
    controller_mode: ControllerMode | int
    controller_ready: bool
    planner: Planner | int
    safety: Safety | int
    safety_message: str
    arms: dict[str, list[float]]

    @property
    def idle(self) -> bool:
        return (self.inference in (Inference.UNINITIALIZED, Inference.CLOSED)
                and self.controller_mode in (ControllerMode.UNSELECTED, ControllerMode.IDLE)
                and self.controller_ready)

    @property
    def healthy(self) -> bool:
        return self.safety == Safety.NO_ERROR

    @property
    def motors_disconnected(self) -> bool:
        return self.safety == Safety.BUS_ERROR or "robot disconnected" in self.safety_message

    def to_json(self) -> dict:
        name = lambda value: value.name if isinstance(value, IntEnum) else value
        return {
            "inference": name(self.inference),
            "controller_mode": name(self.controller_mode),
            "controller_ready": self.controller_ready,
            "planner": name(self.planner),
            "safety": name(self.safety),
            "safety_message": self.safety_message,
            "idle": self.idle,
            "healthy": self.healthy,
            "arms": {arm: [round(v, 4) for v in pose] for arm, pose in self.arms.items()},
        }


def read_status(bridge: RosBridge) -> RobotStatus:
    latest = bridge.latest
    controller = latest[CONTROLLER_STATUS]
    safety = latest[SAFETY_STATE]
    return RobotStatus(
        inference=_named(Inference, latest[INFERENCE_STATUS]["infer_state"]),
        controller_mode=_named(ControllerMode, controller["mode"]),
        controller_ready=controller["ready"],
        planner=_named(Planner, controller["motion_planner_status"]),
        safety=_named(Safety, safety["robot_state"]),
        safety_message=safety.get("error_msg", ""),
        arms={arm: arm_pose(latest[ARM_POSES[arm]], latest[GRIPPERS[arm]]) for arm in ARM_POSES},
    )


def model_info(prompt: str, model_address: str) -> dict:
    """The JSON the robot client receives with INIT_MODEL: where the model is and how to run it."""
    return {
        "model_address": model_address,
        "model_name": "squarex",
        "robot_type": "desktop",
        "robot_mode": "end_pose",
        "instruction": prompt,
        "infer_type": "sync",
        "infer_params": INFER_PARAMS,
    }


def control_inference(bridge: RosBridge, command: InferenceCommand, model: dict | None = None, timeout: float = 15) -> None:
    request = {"infer_cmd": int(command), "model_info_json": json.dumps(model) if model else "", "model_trigger_enabled": False}
    if not bridge.call(INFERENCE_CONTROL, request, timeout).get("success"):
        raise RosError(f"inference_control {command.name} was rejected")


def switch_controller_mode(bridge: RosBridge, mode: ControllerMode) -> None:
    if bridge.call(SWITCH_CONTROLLER_MODE, {"mode": int(mode)}).get("status") != 1:
        raise RosError(f"switch_controller_mode {mode.name} was rejected")
