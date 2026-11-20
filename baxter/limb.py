"""
Baxter Limb Controller - Individual Arm Motion & Joint Jogging.
"""

import math
import asyncio
from typing import Dict, List, Union, Optional

from .poses import JOINTS, LIMITS


class Limb:
    """Controls a single 7-DOF Baxter arm (left or right)."""

    def __init__(self, baxter: "Baxter", name: str):
        self.baxter = baxter
        self.name = name.lower()
        if self.name not in ("left", "right"):
            raise ValueError(f"Limb name must be 'left' or 'right', got {name}")
        self.joint_names = JOINTS[self.name]

    async def get_joint_positions(self) -> Dict[str, float]:
        """Returns dictionary of joint positions for this limb."""
        return await self.baxter.get_joint_positions(self.name)

    async def suppress_collision_avoidance(self):
        """Suppresses internal collision avoidance for this limb."""
        await self.baxter.publish(f"/robot/limb/{self.name}/suppress_collision_avoidance", {})

    async def move_to(
        self,
        target: Union[List[float], Dict[str, float]],
        duration: float = 3.5
    ):
        """Moves this limb to target joint angles."""
        if self.name == "left":
            await self.baxter.move_to(left=target, duration=duration)
        else:
            await self.baxter.move_to(right=target, duration=duration)

    async def jog(self, joint_name_or_short: str, delta_rad: float = 0.0, delta_deg: Optional[float] = None, duration: float = 2.0):
        """
        Jogs a single joint by delta radians or degrees.
        joint_name_or_short: e.g. 's0', 'left_s0', 'e1', 'w2'
        """
        if delta_deg is not None:
            delta_rad = math.radians(delta_deg)

        if not joint_name_or_short.startswith(f"{self.name}_"):
            full_name = f"{self.name}_{joint_name_or_short}"
        else:
            full_name = joint_name_or_short

        if full_name not in self.joint_names:
            raise ValueError(f"Unknown joint {full_name}. Valid joints for {self.name}: {self.joint_names}")

        short_name = full_name.replace(f"{self.name}_", "")
        limits = LIMITS.get(short_name, (-3.0, 3.0))

        current = await self.get_joint_positions()
        curr_pos = current.get(full_name, 0.0)
        target_pos = curr_pos + delta_rad

        # Enforce safety limits
        clamped_pos = max(limits[0], min(limits[1], target_pos))

        targets = [current.get(j, 0.0) for j in self.joint_names]
        idx = self.joint_names.index(full_name)
        targets[idx] = clamped_pos

        await self.move_to(targets, duration=duration)
        return clamped_pos
