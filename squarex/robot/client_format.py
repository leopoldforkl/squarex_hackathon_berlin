"""Messages of the robot client (msgpack, its own "legacy" layout) <-> Observation / Actions."""
import base64
from dataclasses import dataclass

import msgpack

from squarex.arrays import to_list

ARM_KEYS = {"left": "follow1_pos", "right": "follow2_pos"}
CAMERA_KEYS = {"front": "camera_front", "left_wrist": "camera_left", "right_wrist": "camera_right"}


@dataclass
class Observation:
    arms: dict[str, list[float]]    # arm -> [x, y, z, roll, pitch, yaw, gripper]
    images: dict[str, bytes]        # view -> JPEG


Actions = dict[str, list[list[float]]]   # arm -> rows of [x, y, z, roll, pitch, yaw, gripper]


def _jpeg(value) -> bytes:
    return base64.b64decode(value.split(",")[-1]) if isinstance(value, str) else bytes(value)


def decode_observation(raw: bytes) -> Observation:
    message = msgpack.unpackb(raw, raw=False, strict_map_key=False)
    return Observation(
        arms={arm: [float(v) for v in to_list(message["state"][key])] for arm, key in ARM_KEYS.items()},
        images={view: _jpeg(message["views"][key]) for view, key in CAMERA_KEYS.items()},
    )


def encode_actions(actions: Actions) -> bytes:
    return msgpack.packb({key: actions[arm] for arm, key in ARM_KEYS.items()}, use_bin_type=True)
