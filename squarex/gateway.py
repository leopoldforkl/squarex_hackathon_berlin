"""The robot client connects here as if this were the model.

Inference mode: robot observation -> model request -> model reply -> robot actions, every step logged.
Ready mode: the gateway answers itself with step-limited moves to the ready pose.
"""
import msgpack
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import ServerConnection, serve

from squarex import runtime
from squarex.config import Settings
from squarex.images import resize
from squarex.models import MODELS
from squarex.robot.client_format import Observation, decode_observation, encode_actions
from squarex.robot.ready_pose import actions_towards_ready_pose
from squarex.runlog import RunLog

READY_METADATA = msgpack.packb({"model": "ready-pose", "env": "x2robot", "action_horizon": 32}, use_bin_type=True)

_metadata_cache: dict[str, bytes] = {}   # sent at once to the next robot connection; it gives up after ~5 s


def run(settings: Settings) -> None:
    with serve(lambda robot: _handle(robot, settings), settings.laptop_ip, settings.gateway_port, max_size=None) as server:
        print(f"gateway listening on {settings.gateway_url}", flush=True)
        server.serve_forever()


def _handle(robot: ServerConnection, settings: Settings) -> None:
    mode, model = runtime.mode(), runtime.model()
    log = RunLog(runtime.run_id(), stream=mode if mode == runtime.READY else model)
    print(f"robot connected ({mode}, {model}), logging to {log.dir}", flush=True)
    try:
        if mode == runtime.READY:
            _serve_ready_pose(robot, log)
        else:
            _serve_model(robot, settings, model, log)
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


def _resized(observation: Observation, step: int, log: RunLog) -> tuple[Observation, dict[str, str]]:
    images = {view: resize(jpeg) for view, jpeg in observation.images.items()}
    files = {view: log.save_image(step, view, jpeg) for view, jpeg in images.items()}
    return Observation(arms=observation.arms, images=images), files


def _serve_model(robot: ServerConnection, settings: Settings, name: str, log: RunLog) -> None:
    model = MODELS[name]
    cached = _metadata_cache.get(name)
    if cached:
        robot.send(cached)
    with model.connect(settings) as socket:
        if not cached:
            robot.send(socket.metadata_raw)
        _metadata_cache[name] = socket.metadata_raw
        log.write(0, f"{name} -> laptop (handshake)", socket.metadata)

        for step, raw in enumerate(robot, start=1):
            observation, image_files = _resized(decode_observation(raw), step, log)
            log.write(step, "robot -> laptop", {"arms": observation.arms, "images": image_files})

            request = model.build_request(observation, runtime.prompt())
            log.write(step, f"laptop -> {name}", request)

            reply = socket.exchange(request)
            log.write(step, f"{name} -> laptop", reply)

            actions = model.read_actions(reply)
            robot.send(encode_actions(actions))
            log.write(step, "laptop -> robot", actions)
