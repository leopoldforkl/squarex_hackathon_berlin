import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
RUNTIME_DIR = ROOT / "runtime"

SSH_KEY = "/ssh/id"
SSH_KNOWN_HOSTS = "/ssh/known_hosts"
MOTOR_DRIVER_CONTAINER = "desktop-desktop_app-1"

EMBODIMENT = "teletwin_desktop/gripper-g"
INFER_PARAMS = {
    "action_horizon": 32,
    "control_dt": 0.005,
    "interpolate_multiplier": 7,
    "async_params": {
        "api_schema": "public_v2",
        "embodiment": EMBODIMENT,
        "normalization": "provided",
        "algorithm": "sync",
    },
}
IMAGE_LONG_SIDE = 448
IMAGE_QUALITY = 80
GRIPPER_RANGE = (0.0, 1.5260001)

# [x, y, z, roll, pitch, yaw, gripper] in each arm's neutral frame (home = all zeros)
READY_POSE = {
    "left": [0.0767, -0.1433, 0.0547, 0.2829, 0.5697, -0.4822, 0.0],
    "right": [0.0767, 0.1433, 0.0547, -0.2829, 0.5697, 0.4822, 0.0],
}
MAX_STEP_MM = 80
MAX_STEP_DEG = 10
READY_TOLERANCE_MM = 10
READY_TOLERANCE_DEG = 4


@dataclass(frozen=True)
class Settings:
    wallx_api_key: str
    wallx_url: str
    local_model_url: str
    robot_ip: str
    laptop_ip: str
    rosbridge_port: int
    gateway_port: int
    ui_port: int
    robot_ssh_user: str

    @property
    def rosbridge_url(self) -> str:
        return f"ws://{self.robot_ip}:{self.rosbridge_port}"

    @property
    def gateway_url(self) -> str:
        return f"ws://{self.laptop_ip}:{self.gateway_port}"

    @property
    def robot_ssh(self) -> str:
        return f"{self.robot_ssh_user}@{self.robot_ip}"


def load_settings() -> Settings:
    env = os.environ
    return Settings(
        wallx_api_key=env["WALLX_API_KEY"],
        wallx_url=env.get("WALLX_URL", "wss://maas-api.x2robot.com/v1/vla/wallx"),
        local_model_url=env.get("LOCAL_MODEL_URL", ""),
        robot_ip=env["ROBOT_IP"],
        laptop_ip=env["LAPTOP_IP"],
        rosbridge_port=int(env.get("ROSBRIDGE_PORT", 9090)),
        gateway_port=int(env.get("GATEWAY_PORT", 8001)),
        ui_port=int(env.get("UI_PORT", 8080)),
        robot_ssh_user=env.get("ROBOT_SSH_USER", "xr"),
    )
