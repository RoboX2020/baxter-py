"""
Baxter Choreographies - Orchestral Symphony and Musical Dance Routines.
"""

import os
import time
import math
import asyncio
import subprocess
from typing import Optional

from .poses import POSES, JOINTS


class SymphonyChoreography:
    """Multi-act classical orchestral symphony choreography."""

    def __init__(self, baxter: "Baxter"):
        self.baxter = baxter

    async def run(self):
        print("=" * 65)
        print("    🎼 STARTING BAXTER 5-ACT ORCHESTRAL SYMPHONY 🎼")
        print("=" * 65)

        # Act 1: The Awakening & Posture Alignment
        print("[Act 1/5] The Awakening & Tuning...")
        await self.baxter.display.show_emotion("neutral", status_text="ACT I: THE AWAKENING")
        await self.baxter.untuck(duration=3.5)
        await self.baxter.head.pan(-0.4)
        await asyncio.sleep(0.5)
        await self.baxter.head.pan(0.4)
        await asyncio.sleep(0.5)
        await self.baxter.head.pan(0.0)
        await self.baxter.head.nod()

        # Act 2: Maestro Baton Conducting (4/4 allegro time)
        print("[Act 2/5] The Maestro Takes The Podium (Allegro 4/4)...")
        await self.baxter.display.show_emotion("focused", status_text="ACT II: THE MAESTRO")
        for bar in range(3):
            # Downbeat
            await self.baxter.move_to(
                left=[-0.20, -0.40, -0.80, 1.40, 0.30, 0.80, 0.0],
                right=[0.20, -0.40, 0.80, 1.40, -0.30, 0.80, 0.0],
                duration=0.6
            )
            # Inward Beat
            await self.baxter.move_to(
                left=[-0.05, -0.60, -0.40, 1.60, 0.10, 0.90, 0.2],
                right=[0.05, -0.60, 0.40, 1.60, -0.10, 0.90, -0.2],
                duration=0.6
            )
            # Outward Beat
            await self.baxter.move_to(
                left=[-0.45, -0.50, -1.00, 1.20, 0.50, 0.70, -0.2],
                right=[0.45, -0.50, 1.00, 1.20, -0.50, 0.70, 0.2],
                duration=0.6
            )
            # Upbeat & Prep
            await self.baxter.move_to(
                left=[-0.15, -0.70, -0.60, 1.80, 0.20, 1.00, 0.0],
                right=[0.15, -0.70, 0.60, 1.80, -0.20, 1.00, 0.0],
                duration=0.6
            )

        # Act 3: Traveling Sine Wave
        print("[Act 3/5] The Kinetic Sine Wave...")
        await self.baxter.display.show_emotion("happy", status_text="ACT III: KINETIC WAVE")
        t0 = time.time()
        while time.time() - t0 < 6.0:
            t = time.time() - t0
            phi_l = t * 3.0
            phi_r = t * 3.0 + math.pi
            left_pose = [-0.15, -0.70 + 0.25 * math.sin(phi_l), -0.60, 1.40 + 0.35 * math.cos(phi_l), 0.20, 0.80, 0.0]
            right_pose = [0.15, -0.70 + 0.25 * math.sin(phi_r), 0.60, 1.40 + 0.35 * math.cos(phi_r), -0.20, 0.80, 0.0]
            await self.baxter.move_to(left=left_pose, right=right_pose, duration=0.12)

        # Act 4: Geometric Kaleidoscope
        print("[Act 4/5] Geometric Kaleidoscope...")
        await self.baxter.display.show_emotion("disco", status_text="ACT IV: KALEIDOSCOPE")
        await self.baxter.cheer(duration=2.5)

        # Act 5: Finale & Grand Bow
        print("[Act 5/5] Grand Finale & Formal Bow...")
        await self.baxter.display.show_emotion("happy", status_text="ACT V: FINALE & BOW")
        await self.baxter.untuck(duration=3.0)
        await self.baxter.head.nod()
        print("[✓] Orchestral Symphony Complete!")


class DanceParty:
    """High-energy 124 BPM musical dance party with neon audio visualizer."""

    def __init__(self, baxter: "Baxter", wav_path: Optional[str] = None):
        self.baxter = baxter
        self.wav_path = wav_path or os.path.join(os.path.dirname(__file__), "..", "models", "baxter_groove.wav")

    async def run(self, play_audio: bool = True):
        print("=" * 65)
        print("   🕺 STARTING BAXTER 124 BPM MUSICAL DANCE PARTY 🕺")
        print("=" * 65)

        # Start background music if available
        audio_proc = None
        if play_audio and os.path.exists(self.wav_path):
            try:
                audio_proc = subprocess.Popen(["aplay", "-q", self.wav_path])
                print(f"[*] Playing backing track: {self.wav_path}")
            except Exception as e:
                print(f"[!] Audio playback notice: {e}")

        try:
            bpm = 124.0
            beat_sec = 60.0 / bpm # ~0.484s

            await self.baxter.display.show_emotion("disco", status_text="GROOVE MODE: 124 BPM")
            await self.baxter.untuck(duration=2.5)

            # Step 1: Up & Down Disco Pump (8 beats)
            print("[*] Beat Section 1: Disco Arm Pumps...")
            for beat in range(4):
                # Arm Up Pump
                await self.baxter.move_to(
                    left=[-0.35, -0.65, -0.50, 1.10, 0.0, 0.40, 0.0],
                    right=[0.35, -0.65, 0.50, 1.10, 0.0, 0.40, 0.0],
                    duration=beat_sec * 0.9
                )
                await self.baxter.head.pan(0.2 if beat % 2 == 0 else -0.2, speed_ratio=0.8)

                # Arm Drop Bounce
                await self.baxter.move_to(
                    left=[-0.15, -0.90, -1.00, 1.85, 0.50, 0.90, -0.3],
                    right=[0.15, -0.90, 1.00, 1.85, -0.50, 0.90, 0.3],
                    duration=beat_sec * 0.9
                )

            # Step 2: Alternating Wave & Cross (8 beats)
            print("[*] Beat Section 2: Alternating Groove Swings...")
            for beat in range(4):
                await self.baxter.move_to(
                    left=[-0.45, -0.50, -0.80, 0.90, 0.20, 0.20, 0.0],
                    right=[0.10, -0.85, 0.40, 1.80, -0.20, 0.80, 0.0],
                    duration=beat_sec * 0.95
                )
                await self.baxter.move_to(
                    left=[-0.10, -0.85, -0.40, 1.80, 0.20, 0.80, 0.0],
                    right=[0.45, -0.50, 0.80, 0.90, -0.20, 0.20, 0.0],
                    duration=beat_sec * 0.95
                )

            # Step 3: High Cheer & Nod Drop
            print("[*] Beat Section 3: High Cheer Climax...")
            await self.baxter.display.show_emotion("happy", status_text="DROP THE BASS! 🎉")
            await self.baxter.move_to(left=POSES["cheer"]["left"], right=POSES["cheer"]["right"], duration=beat_sec * 2.0)
            await self.baxter.head.nod()
            await asyncio.sleep(beat_sec * 2.0)

            # Finale: Symmetrical Return
            print("[*] Beat Section 4: Return to Neutral...")
            await self.baxter.untuck(duration=beat_sec * 3.0)
            await self.baxter.head.pan(0.0)
            await self.baxter.display.show_emotion("neutral", status_text="DANCE COMPLETED! THANK YOU!")
            print("[✓] Dance Party Completed Successfully!")

        finally:
            if audio_proc:
                try:
                    audio_proc.terminate()
                except Exception:
                    pass
