"""WALLX cloud model: Observation / Actions <-> public_v2."""
from squarex.arrays import to_list
from squarex.config import EMBODIMENT, GRIPPER_RANGE, Settings
from squarex.models.socket import ModelSocket
from squarex.robot.client_format import Actions, Observation


def connect(settings: Settings) -> ModelSocket:
    return ModelSocket(settings.wallx_url, headers={"Authorization": f"Bearer {settings.wallx_api_key}"})


def build_request(observation: Observation, prompt: str) -> dict:
    return {
        "embodiment": EMBODIMENT,
        "normalization": "provided",
        "instruction": prompt,
        "observation": {
            "images": observation.images,
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
