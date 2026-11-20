"""
UNTESTED sample: apply a baxter-py pose to a Baxter articulation in Isaac Sim.

Run inside Isaac Sim's Script Editor (Window -> Script Editor) after importing
sim/baxter_isaac.urdf and saving the stage as USD. API module names differ
between Isaac Sim releases (omni.isaac.core vs isaacsim.core.api); adjust the
imports for your version. This file has NOT been executed.
"""

import json
import os

# Isaac Sim 4.5+/5.x style imports; older releases use omni.isaac.core instead.
from isaacsim.core.api.world import World
from isaacsim.core.api.articulations import Articulation

POSES_PATH = os.path.join(os.path.dirname(__file__), "poses.json")
ARTICULATION_PRIM = "/World/baxter"  # adjust to your stage's prim path


def apply_pose(pose_name: str, subkey: str | None = None) -> None:
    with open(POSES_PATH) as f:
        data = json.load(f)

    pose = data["poses"][pose_name]
    if subkey:  # e.g. pose "wave", subkey "ready" / "wave_left" / "wave_right"
        pose = pose[subkey]

    world = World.instance()
    baxter = Articulation(prim_paths_expr=ARTICULATION_PRIM, name="baxter")
    world.reset()

    joint_names = list(baxter.dof_names)
    targets = list(baxter.get_joint_positions())

    for side in ("left", "right"):
        ordered = data["joints"][side]  # s0, s1, e0, e1, w0, w1, w2
        values = pose.get(side)
        if values is None:
            continue
        for name, value in zip(ordered, values):
            targets[joint_names.index(name)] = value

    baxter.set_joint_position_targets(targets)


if __name__ == "__main__":
    apply_pose("neutral")
    # apply_pose("wave", "ready")
