"""Observation / Actions <-> WALLX public_v2 messages."""
import io

from PIL import Image

from squarex.arrays import to_list
from squarex.config import EMBODIMENT, IMAGE_LONG_SIDE, IMAGE_QUALITY
from squarex.robot.client_format import Actions, Observation

GRIPPER_RANGE = (0.0, 1.5260001)


def compress(jpeg: bytes) -> bytes:
    with Image.open(io.BytesIO(jpeg)) as image:
        image.thumbnail((IMAGE_LONG_SIDE, IMAGE_LONG_SIDE), Image.Resampling.BOX)
        output = io.BytesIO()
        image.convert("RGB").save(output, "JPEG", quality=IMAGE_QUALITY)
    return output.getvalue()


def build_request(observation: Observation, prompt: str) -> dict:
    return {
        "embodiment": EMBODIMENT,
        "normalization": "provided",
        "instruction": prompt,
        "observation": {
            "images": {view: compress(jpeg) for view, jpeg in observation.images.items()},
            "state": {
                f"{arm}_ee": {"position": pose[:3], "rotation_rpy": pose[3:6], "gripper": pose[6]}
                for arm, pose in observation.arms.items()
            },
        },
    }


def read_actions(reply: dict) -> Actions:
    actions = {}
    for arm in ("left", "right"):
        block = reply["actions"][f"{arm}_ee"]
        positions, rotations, grippers = (to_list(block[key]) for key in ("position", "rotation_rpy", "gripper"))
        if not all(GRIPPER_RANGE[0] <= g <= GRIPPER_RANGE[1] for g in grippers):
            raise ValueError(f"{arm} gripper outside {GRIPPER_RANGE}: {grippers}")
        actions[arm] = [[*p, *r, g] for p, r, g in zip(positions, rotations, grippers)]
    return actions
