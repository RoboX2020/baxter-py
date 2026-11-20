#!/usr/bin/env python3
"""
Example 05: Orchestral Symphony and Musical Dance Parties.
Runs high-level choreographed routines.
"""

import asyncio
from baxter import Baxter
from baxter.choreography import SymphonyChoreography, DanceParty

async def main():
    async with Baxter() as robot:
        state = await robot.get_state()
        if not state.get("enabled"):
            await robot.enable()

        print("Executing 5-Act Orchestral Symphony...")
        symphony = SymphonyChoreography(robot)
        await symphony.run()

        print("\nExecuting Musical Dance Party...")
        dance = DanceParty(robot)
        await dance.run(play_audio=True)

if __name__ == "__main__":
    asyncio.run(main())
