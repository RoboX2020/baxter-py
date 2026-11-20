#!/usr/bin/env python3
"""
Example 01: Status, Interlocks, and Motor Control.
Demonstrates connecting to Baxter, reading hardware states, and enabling motors.
"""

import asyncio
from baxter import Baxter

async def main():
    async with Baxter() as robot:
        print(f"Connected to Baxter at {robot.ws_url}")

        # 1. Read assembly state
        state = await robot.get_state()
        print(f"Motors Enabled: {state.get('enabled')}")
        print(f"Robot Stopped:  {state.get('stopped')}")
        print(f"E-Stop Button:  {state.get('estop_button')}")

        # 2. Read joint angles
        joints = await robot.get_joint_positions()
        print(f"\nTotal joints reported: {len(joints)}")
        print(f"Left shoulder s0: {joints.get('left_s0', 0.0):.3f} rad")
        print(f"Right shoulder s0: {joints.get('right_s0', 0.0):.3f} rad")

        # 3. Ensure motors are enabled
        if not state.get('enabled'):
            print("\nEnabling motors...")
            success = await robot.enable()
            print(f"Enable successful: {success}")

if __name__ == "__main__":
    asyncio.run(main())
