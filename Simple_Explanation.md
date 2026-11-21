# How the cloud communication works (simple version)

The robot can't think for itself. Each time around, it:

1. takes 3 photos and notes where its two arms are,
2. sends that to the laptop,
3. the laptop adds the task in words ("Pick up the cube.") and sends it all to the WALLX cloud,
4. the cloud sends back a short plan: the next 32 positions for each arm,
5. the laptop passes that plan to the robot, which moves along it,
6. and then it all starts again.

The laptop acts as a **translator** (`squarex/gateway.py`). The robot and the cloud use different message formats,
so the laptop rewrites every message in both directions. Every message is binary **msgpack** (a compact form of
JSON) sent over a **WebSocket**. The examples below are written out as JSON so you can read them. The values are
real ones from `logs/20261121-224046/cloud.jsonl`, shortened.

```
robot ──msgpack/ws──► laptop gateway (:8001) ──msgpack/wss──► WALLX cloud
      ◄── 32 steps ──                         ◄── 32 steps ──
```

---

## 1. Handshake: "hello, who are you?"

The laptop opens a connection to the cloud and shows its API key (`squarex/cloud/wallx.py`):

```
wss://maas-api.x2robot.com/v1/vla/wallx
Authorization: Bearer <WALLX_API_KEY>
```

Before the laptop sends anything, the cloud introduces itself:

```json
{
  "model": "wall-x",
  "model_version": "2610-dualhead-v2",
  "checkpoint": "0_137500",
  "robot_type": "desktop",
  "action_horizon": 32,
  "row_dt_s": 0.0337
}
```

This means: "I'm wall-x. Each answer gives you **32 steps**, and each step lasts about **34 ms**."
The laptop forwards this message unchanged to the robot. (The log keeps only these six fields of the handshake.)

---

## 2. Input: what the laptop sends the cloud (one per step)

Built by `build_request` in `squarex/cloud/protocol.py`:

```json
{
  "embodiment": "teletwin_desktop/gripper-g",
  "normalization": "provided",
  "instruction": "Pick up the cube.",
  "observation": {
    "images": {
      "front":       "<JPEG bytes, ~25 KB>",
      "left_wrist":  "<JPEG bytes, ~33 KB>",
      "right_wrist": "<JPEG bytes>"
    },
    "state": {
      "left_ee": {
        "position":     [0.0764, -0.1425, 0.0551],
        "rotation_rpy": [0.2664,  0.5684, -0.4743],
        "gripper":      -0.0002
      },
      "right_ee": {
        "position":     [0.0772,  0.1425, 0.0557],
        "rotation_rpy": [-0.2671, 0.5595, 0.4711],
        "gripper":      -0.0006
      }
    }
  }
}
```

| Field | Meaning |
|---|---|
| `embodiment` | which kind of robot this is |
| `instruction` | the task in plain words (read from `runtime/prompt` at every step, so you can change it while a run is going) |
| `images` | 3 camera photos, shrunk to at most 448 px wide, JPEG quality 80 |
| `position` | where the hand is, x/y/z in metres |
| `rotation_rpy` | how the hand is tilted (roll/pitch/yaw, in radians) |
| `gripper` | 0 = closed … 1.526 = fully open |

---

## 3. Output: what the cloud sends back

```json
{
  "embodiment": "teletwin_desktop/gripper-g",
  "normalization": "provided",
  "actions": {
    "left_ee": {
      "position":     [[0.0818, -0.1458, 0.0554], [0.0833, -0.1470, 0.0533], "... 32 rows"],
      "rotation_rpy": [[0.2638,  0.5517, -0.4614], [0.2650,  0.5573, -0.4585], "... 32 rows"],
      "gripper":      [0.0009, 0.0019, 0.0021, "... 32 values"]
    },
    "right_ee": {
      "position":     [[0.0827, 0.1464, 0.0534], [0.0846, 0.1478, 0.0503], "... 32 rows"],
      "rotation_rpy": [[-0.2871, 0.5560, 0.4359], [-0.2960, 0.5678, 0.4253], "... 32 rows"],
      "gripper":      [0.0010, 0.0011, 0.0021, "... 32 values"]
    }
  },
  "server_timing": { "infer_ms": 67.6, "queue_wait_ms": 0.004, "active_robots": 2 },
  "usage":         { "input_tokens": 649, "output_tokens": 32, "total_tokens": 681 },
  "_sampling":     { "request_id": "a6cd9a5f…", "seed": "6059570236304603168", "...": "debug info" }
}
```

It's the same layout as the input, except each value is now a **list of 32 steps**: "first go here, then here,
then here…". The other blocks (`server_timing`, `usage`, `_sampling`, plus one called `cb_rtc`) are information
about the request itself, and the laptop ignores them. If the reply has an `"error"` key instead, the gateway stops
and closes the robot's connection.

---

## 4. What the robot finally gets

`read_actions` (`squarex/cloud/protocol.py`) puts each step's position, rotation and gripper together into one row of
7 numbers, `[x, y, z, roll, pitch, yaw, gripper]`, and rejects gripper values outside 0–1.526. `encode_actions`
(`squarex/robot/client_format.py`) then uses the robot's own names for the arms:

```json
{
  "follow1_pos": [[0.0818, -0.1458, 0.0554, 0.2638, 0.5517, -0.4614, 0.0009], "... 32 rows"],
  "follow2_pos": [[0.0827,  0.1464, 0.0534, -0.2871, 0.5560, 0.4359, 0.0010], "... 32 rows"]
}
```

`follow1` is the left arm and `follow2` is the right arm.

---

## Where the time goes

| Step | Sent | Answer back | Cloud's own compute time |
|---|---|---|---|
| 1 | 22:41:09 | 22:41:21 | 68 ms |
| 2 | 22:41:22 | 22:41:26 | 82 ms |
| 5 | 22:41:40 | 22:41:52 | 80 ms |

The cloud says it needs only about **80 ms** to compute an answer, yet each round trip took **4–12 seconds**.
The delay comes from somewhere between the laptop and the GPU: the upload, the network, or queuing in front of the
model. The log only records whole seconds, so it can't tell which one.
