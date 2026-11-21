# squarex hackathon berlin

Runs the squarex desktop robot (two arms, three cameras) with the **WALLX cloud model**.
A CLI does all the work; the web page only calls the CLI.

```
           laptop                                                      robot (192.168.77.2)
┌──────────────────────────────────────────────┐            ┌───────────────────────────────┐
│ ui (web page) ──calls──► cli                  │  rosbridge │ ROS 2: start/stop inference,   │
│                          └─ robot/procedures ─┼──JSON/ws──►│ controller modes, robot state  │
│                                               │            │                               │
│ gateway ◄────────────────────────────────────┼──msgpack───│ robot client (cameras + arms)  │
│   ├─ robot/client_format  (robot ⇄ Observation/Actions)    └───────────────────────────────┘
│   └─ cloud/protocol + wallx ──public_v2/wss──► WALLX cloud model
└──────────────────────────────────────────────┘
```

## Setup

```bash
cp .env.example .env    # API key, IPs, ports, ssh key for the robot
make build
make up                 # gateway + ui (http://127.0.0.1:8080)
```

## CLI

```bash
make cli ARGS='status'
make cli ARGS='start "pick up the can" --seconds 90'   # ready pose first, then the model
make cli ARGS='prompt "put the can on the book"'       # takes effect at the next model step
make cli ARGS='stop'
make cli ARGS='home'
make cli ARGS='clear-bus-error'                         # CAN adapters dropped out and came back
```

`start` runs: ready pose → `INIT_MODEL` (model = this laptop's gateway) → controller mode `POSE_INFERENCE`
→ `START` → watch until the time limit, a stop, or a fault → `STOP`, `CLOSE` → controller mode `IDLE`.

## Code

| Path | Job |
|---|---|
| `squarex/cli.py` | the commands |
| `squarex/robot/rosbridge.py` | JSON WebSocket to rosbridge |
| `squarex/robot/ros.py` | ROS topics and services ⇄ plain Python values |
| `squarex/robot/procedures.py` | start, stop, home, ready pose, clear bus error |
| `squarex/robot/client_format.py` | robot client messages ⇄ `Observation` / `Actions` |
| `squarex/robot/ready_pose.py` | step-limited moves to the ready pose |
| `squarex/cloud/protocol.py` | `Observation` / `Actions` ⇄ WALLX public_v2 |
| `squarex/cloud/wallx.py` | WALLX WebSocket client |
| `squarex/gateway.py` | robot client ⇄ cloud, one step at a time |
| `squarex/ui/` | web page that runs CLI commands |
| `squarex/config.py` | `.env` settings and robot/model constants |

## Logs

```
logs/ros.jsonl                      every ROS service call: request and response
logs/<run>/cloud.jsonl              per model step: robot → laptop → cloud → laptop → robot
logs/<run>/ready.jsonl              moves to the ready pose
logs/<run>/images/<step>-<view>.jpg images as sent to the cloud
```

## Coordinates

Arm poses are `[x, y, z, roll, pitch, yaw, gripper]` in each arm's neutral frame
(metres, radians, R = Rz(yaw)·Ry(pitch)·Rx(roll)); home is all zeros. Gripper G: 0 closed … 1.526 open.
