"""Local wall-x server: Observation / Actions <-> the robot client's own layout, which the server reads directly."""
import base64

from squarex.arrays import to_list
from squarex.config import GRIPPER_RANGE, Settings
from squarex.models.socket import ModelSocket
from squarex.robot.client_format import ARM_KEYS, CAMERA_KEYS, Actions, Observation


def connect(settings: Settings) -> ModelSocket:
    return ModelSocket(settings.local_model_url)


def build_request(observation: Observation, prompt: str) -> dict:
    return {
        "state": {key: observation.arms[arm] for arm, key in ARM_KEYS.items()},
        "views": {key: base64.b64encode(observation.images[view]).decode() for view, key in CAMERA_KEYS.items()},
        "instruction": prompt,
    }


def _clamp_gripper(row: list[float]) -> list[float]:
    return [*row[:6], min(max(row[6], GRIPPER_RANGE[0]), GRIPPER_RANGE[1])]


def read_actions(reply: dict) -> Actions:
    """The server answers with 33 rows per arm (row 0 = current pose); its gripper values can exceed gripper G."""
    return {arm: [_clamp_gripper(row) for row in to_list(reply[key])] for arm, key in ARM_KEYS.items()}
