"""Step-limited trajectories to the ready pose, served by the gateway in place of a model."""
import math

from squarex.config import MAX_STEP_DEG, MAX_STEP_MM, READY_POSE
from squarex.robot.client_format import Actions, Observation

ROWS = 32


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def distance(pose: list[float], target: list[float]) -> tuple[float, float]:
    """(position error in mm, largest angle error in degrees)"""
    millimetres = math.dist(pose[:3], target[:3]) * 1000
    degrees = max(abs(math.degrees(_wrap(target[i] - pose[i]))) for i in (3, 4, 5))
    return millimetres, degrees


def _trajectory(pose: list[float], target: list[float]) -> list[list[float]]:
    delta = [target[i] - pose[i] for i in range(3)] + [_wrap(target[i] - pose[i]) for i in (3, 4, 5)] + [target[6] - pose[6]]
    millimetres, degrees = distance(pose, target)
    scale = min(1.0, MAX_STEP_MM / millimetres if millimetres else 1.0, MAX_STEP_DEG / degrees if degrees else 1.0)
    rows = []
    for i in range(1, ROWS + 1):
        u = i / ROWS
        smooth = scale * (3 * u * u - 2 * u * u * u)
        row = [pose[j] + delta[j] * smooth for j in range(7)]
        row[6] = max(row[6], 0.0)
        rows.append(row)
    return rows


def actions_towards_ready_pose(observation: Observation) -> Actions:
    return {arm: _trajectory(observation.arms[arm], READY_POSE[arm]) for arm in READY_POSE}


def reached(arms: dict[str, list[float]], tolerance_mm: float, tolerance_deg: float) -> bool:
    return all(
        millimetres <= tolerance_mm and degrees <= tolerance_deg
        for millimetres, degrees in (distance(arms[arm], READY_POSE[arm]) for arm in READY_POSE)
    )
