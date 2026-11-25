# Joint map: baxter-py <-> Baxter URDF

`baxter-py` names joints exactly as the URDF does, so no renaming is needed.

| baxter-py joint | URDF joint | Type | URDF limits (rad) |
|---|---|---|---|
| left_s0 / right_s0 | same | revolute | -1.702 .. 1.702 |
| left_s1 / right_s1 | same | revolute | -2.147 .. 1.047 |
| left_e0 / right_e0 | same | revolute | -3.054 .. 3.054 |
| left_e1 / right_e1 | same | revolute | -0.050 .. 2.618 |
| left_w0 / right_w0 | same | revolute | -3.059 .. 3.059 |
| left_w1 / right_w1 | same | revolute | -1.571 .. 2.094 |
| left_w2 / right_w2 | same | revolute | -3.059 .. 3.059 |
| (head pan) | head_pan | revolute | -1.571 .. 1.571 |
| (head nod) | head_nod | FIXED in URDF | n/a |

Verified 2026-11-20: limits in `baxter/poses.py` match the URDF for all 14 arm
joints. `poses.json` carries the same values.

Notes:
- `poses.json` joint arrays are ordered s0, s1, e0, e1, w0, w1, w2 per arm.
- The URDF's fixed `*_endpoint`, `*_hand`, camera and sensor frames import as
  fixed joints/links and need no drives.
- Command modes: the real Baxter accepts position, velocity and torque
  JointCommand modes. Isaac articulations use per-joint position/velocity drive
  targets; torque mode has no direct equivalent and would need a custom
  controller.
