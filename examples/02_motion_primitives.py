#!/usr/bin/env python3
"""
Example 02: Motion Primitives and Arm Jogging.
Demonstrates untuck, waving, cheering, and individual joint jogging.
"""

import asyncio
from baxter import Baxter

async def main():
    async with Baxter() as robot:
        # Verify motors are enabled
        state = await robot.get_state()
        if not state.get("enabled"):
            await robot.enable()

        print("[1] Moving to symmetrical neutral pose...")
        await robot.untuck(duration=3.5)

        print("[2] Executing friendly wave with right arm...")
        await robot.wave(cycles=2)

        print("[3] Raising both arms in victory cheer...")
        await robot.cheer(duration=3.0)

        print("[4] Jogging right elbow e0 by +15 degrees...")
        new_angle = await robot.right_arm.jog("e0", delta_deg=15.0)
        print(f"New right elbow e0 angle: {new_angle:.3f} rad")

        print("[5] Returning to neutral posture...")
        await robot.untuck(duration=3.0)
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
