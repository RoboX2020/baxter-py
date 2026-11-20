# Baxter in Isaac Sim

Everything needed to load a Baxter Research Robot model into NVIDIA Isaac Sim and
start testing `baxter-py` poses in simulation, without a real robot.

**Status: UNTESTED.** These assets and instructions are prepared from the upstream
robot model and the official Isaac Sim URDF importer documentation. They have not
yet been executed inside Isaac Sim. Expect to tune import settings and joint drive
gains on first run.

## Contents

| Path | What it is |
|---|---|
| `baxter_upstream.urdf` | Verbatim upstream Baxter URDF from Rethink Robotics' `baxter_common` (uses ROS `package://` mesh paths; kept for provenance). |
| `baxter_isaac.urdf` | Same robot, with mesh paths rewritten to relative `meshes/` so no ROS package resolution is needed. Import THIS one. |
| `meshes/` | The 13 COLLADA meshes the URDF references (visual + collision). Unreferenced STL duplicates, xacro sources and ROS build files from upstream are omitted; get them from the upstream repo if needed. |
| `package.xml.baxter_description` | Upstream package metadata (version, maintainers) for provenance. |
| `LICENSE.baxter_description` | BSD 3-Clause license for the robot model assets (Rethink Robotics). |
| `isaac/poses.json` | Joint names, joint limits and the full `baxter-py` pose library (neutral, tuck, wave, reach, cheer, salute, boxing), extracted from `baxter/poses.py`. All 14 arm joint limits verified to match the URDF. |
| `isaac/joint_map.md` | How `baxter-py` joints map to URDF joints, plus control notes. |
| `isaac/set_poses.py` | Sample Isaac Sim script that applies a pose from `poses.json`. UNTESTED. |

## Quickstart

1. Open Isaac Sim (current 4.x/5.x releases) and enable the **URDF Importer**
   extension (`isaacsim.asset.importer.urdf`) if it is not already on.
2. Import `sim/baxter_isaac.urdf` (File -> Import, or the URDF Importer panel).
   Recommended starting settings:
   - Fix base link: ON (Baxter's pedestal is its base)
   - Joint drive type: Position
   - Self collision: OFF to start
   - Leave default stiffness/damping, then tune (see Known gaps)
3. Save the result as a USD stage.
4. Sanity check: the model should have 15 revolute joints
   (7 per arm plus `head_pan`) and stand on its pedestal.
5. Apply a pose from `isaac/poses.json` (see `isaac/set_poses.py`), e.g. `neutral`,
   then `wave.ready`, and confirm the arms move where you expect.

## Known gaps / not yet verified

- **Nothing here has been run in Isaac Sim yet.** First import may need importer
  setting tweaks; mesh materials and collision meshes are untested.
- **Gravity sag.** The real Baxter runs gravity compensation. A stock URDF import
  with default drive gains will likely sag or drift; increase joint drive
  stiffness or add a gravity-compensation controller before judging motion.
- **Head nod is fixed.** The URDF models `head_nod` as a fixed joint; only
  `head_pan` is actuated. `baxter-py`'s `head nod` command has no sim equivalent.
- **No grippers.** End-effector/gripper models live in separate upstream xacro
  files and are not included.
- **Screen, cameras, sonar, LEDs** are plain links/sensor frames in the URDF.
  `baxter-py`'s display, camera and vision features are real-hardware only.

## Driving the sim with the `baxter` CLI (future work, unverified)

`baxter-py` talks rosbridge WebSocket to the real robot's ROS 1 master. Isaac Sim
speaks native ROS 2. Making the existing CLI drive the simulated Baxter needs:

1. Isaac Sim's ROS 2 bridge publishing/subscribing Baxter-named topics,
2. Baxter message definitions for ROS 2 (e.g. the `baxter_common_ros2` port),
3. a rosbridge_server on that ROS 2 graph so `baxter-py` can connect to localhost,
4. an adapter mapping Baxter's `JointCommand` modes (position / velocity / torque)
   onto Isaac articulation controllers, and publishing `joint_states` feedback.

That adapter does not exist yet and rosbridge alone does not provide it.
Until it is built and tested, use the pose JSON + articulation controller route
above.

## Provenance and license

- Robot model: [RethinkRobotics/baxter_common](https://github.com/RethinkRobotics/baxter_common)
  (`baxter_description`), BSD 3-Clause. Copyright (c) 2013-2015 Rethink Robotics.
  License text retained in `LICENSE.baxter_description` as required.
- Everything else in `sim/isaac/` is part of `baxter-py` (MIT).
