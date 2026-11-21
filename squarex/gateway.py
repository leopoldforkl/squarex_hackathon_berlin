"""The robot client connects here as if this were the model.

Cloud mode: robot observation -> WALLX request -> WALLX reply -> robot actions, every step logged.
Ready mode: the gateway answers itself with step-limited moves to the ready pose.
"""
import msgpack
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import ServerConnection, serve

from squarex import runtime
from squarex.cloud import protocol
from squarex.cloud.wallx import Wallx
from squarex.config import Settings
from squarex.robot.client_format import decode_observation, encode_actions
from squarex.robot.ready_pose import actions_towards_ready_pose
from squarex.runlog import RunLog

READY_METADATA = msgpack.packb({"model": "ready-pose", "env": "x2robot", "action_horizon": 32}, use_bin_type=True)
METADATA_FIELDS = ("model", "model_version", "checkpoint", "robot_type", "action_horizon", "row_dt_s")

_cloud_metadata: bytes | None = None   # sent at once to the next robot connection; it gives up after ~5 s


def run(settings: Settings) -> None:
    with serve(lambda robot: _handle(robot, settings), settings.laptop_ip, settings.gateway_port, max_size=None) as server:
        print(f"gateway listening on {settings.gateway_url}", flush=True)
        server.serve_forever()


def _handle(robot: ServerConnection, settings: Settings) -> None:
    mode = runtime.mode()
    log = RunLog(runtime.run_id(), stream=mode)
    print(f"robot connected ({mode}), logging to {log.dir}", flush=True)
    try:
        if mode == runtime.READY:
            _serve_ready_pose(robot, log)
        else:
            _serve_cloud(robot, settings, log)
    except ConnectionClosed:
        pass   # the robot client closes the connection on STOP / CLOSE
    except Exception as error:
        log.write(0, "error", repr(error))
        print(f"gateway error: {error!r}", flush=True)
        robot.close(code=1011, reason="model unavailable")
    finally:
        log.close()


def _serve_ready_pose(robot: ServerConnection, log: RunLog) -> None:
    robot.send(READY_METADATA)
    for step, raw in enumerate(robot, start=1):
        observation = decode_observation(raw)
        log.write(step, "robot -> laptop", {"arms": observation.arms})
        actions = actions_towards_ready_pose(observation)
        robot.send(encode_actions(actions))
        log.write(step, "laptop -> robot", actions)


def _serve_cloud(robot: ServerConnection, settings: Settings, log: RunLog) -> None:
    global _cloud_metadata
    if _cloud_metadata:
        robot.send(_cloud_metadata)
    with Wallx(settings) as cloud:
        if not _cloud_metadata:
            robot.send(cloud.metadata_raw)
        _cloud_metadata = cloud.metadata_raw
        log.write(0, "cloud -> laptop (handshake)", {key: cloud.metadata.get(key) for key in METADATA_FIELDS})

        for step, raw in enumerate(robot, start=1):
            observation = decode_observation(raw)
            log.write(step, "robot -> laptop", {"arms": observation.arms, "images": sorted(observation.images)})

            request = protocol.build_request(observation, runtime.prompt())
            images = request["observation"]["images"]
            log.write(step, "laptop -> cloud", {**request, "observation": {
                **request["observation"], "images": {view: log.save_image(step, view, jpeg) for view, jpeg in images.items()}}})

            reply = cloud.infer(request)
            log.write(step, "cloud -> laptop", reply)

            actions = protocol.read_actions(reply)
            robot.send(encode_actions(actions))
            log.write(step, "laptop -> robot", actions)
