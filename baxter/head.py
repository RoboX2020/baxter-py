"""
Baxter Head Controller - Pan, Nod, and Gaze Tracking.
"""

import asyncio
from typing import Optional


class Head:
    """Controls Baxter's pan and nod motions."""

    def __init__(self, baxter: "Baxter"):
        self.baxter = baxter

    async def pan(self, angle_rad: float, speed_ratio: float = 0.5):
        """
        Pans head to angle in radians.
        Range: approximately -1.57 rad (turn right) to +1.57 rad (turn left).
        """
        clamped_angle = max(-1.57, min(1.57, angle_rad))
        await self.baxter.publish("/robot/head/command_head_pan", {
            "target": clamped_angle,
            "speed_ratio": max(0.1, min(1.0, speed_ratio)),
            "enable_pan_request": 1
        })

    async def nod(self):
        """Triggers a single head nod gesture."""
        await self.baxter.publish("/robot/head/command_head_nod", {"data": True})

    async def get_pan_angle(self) -> float:
        """Reads current head pan angle in radians."""
        joints = await self.baxter.get_joint_positions()
        return joints.get("head_pan", 0.0)
