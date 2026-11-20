#!/usr/bin/env python3
"""
Example 03: LCD Screen & Vector Face Expressions.
Demonstrates cycling through vector facial expressions and custom banners.
"""

import asyncio
from baxter import Baxter

async def main():
    async with Baxter() as robot:
        emotions = ["neutral", "happy", "focused", "wink", "disco", "boxing", "sleepy"]

        print("Cycling through Baxter face expressions on 1024x600 screen:")
        for emo in emotions:
            print(f"  -> Showing emotion: {emo}")
            await robot.display.show_emotion(
                emotion=emo,
                status_text=f"BAXTER-PY DEMO | MODE: {emo.upper()}"
            )
            await asyncio.sleep(2.0)

        # Reset to friendly happy face
        await robot.display.show_emotion("happy", status_text="BAXTER ONLINE AND READY")
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
