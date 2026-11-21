"""
Baxter Interactive Arena - Multi-Mode HRI Gaming and Teleoperation Suite.
Featuring:
  1. Rock-Paper-Scissors Showdown with audio countdown and animated reactions
  2. Arcade Reflex Boxer 2.0 with sound effects, combos, and parrying
  3. Real-Time Jedi Teleoperation / Shadow Puppeteer (live arm mimicry)
  4. Interactive High-Five & Fist Bump partner
"""

import os
import sys
import time
import math
import base64
import random
import asyncio
import subprocess
from typing import Optional, Tuple, List, Dict, Union
import numpy as np
import cv2

from .poses import JOINTS, POSES, LIMITS
from .vision import GestureDetector, draw_hand_skeleton, HAND_CONNECTIONS
from .display import Display, WIDTH as DISP_W, HEIGHT as DISP_H

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "sounds")


def play_sound(sound_name: str):
    """Asynchronously plays a sound effect via aplay non-blockingly."""
    path = os.path.join(SOUNDS_DIR, f"{sound_name}.wav")
    if os.path.exists(path):
        try:
            subprocess.Popen(["aplay", "-q", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# Pre-defined poses for Arena games
ARENA_POSES = {
    # Rock-Paper-Scissors
    "rps_ready": {
        "left":  [-0.15, -0.75, -0.60, 1.80,  0.20,  0.80,  0.00],
        "right": [ 0.15, -0.75,  0.60, 1.80, -0.20,  0.80,  0.00]
    },
    "rps_pump": {
        "left":  [-0.20, -0.50, -0.50, 1.30,  0.10,  0.60,  0.00],
        "right": [ 0.20, -0.50,  0.50, 1.30, -0.10,  0.60,  0.00]
    },
    "rps_rock": {
        "left":  [-0.15, -0.70, -0.60, 2.05,  0.30,  0.50, -0.20],
        "right": [ 0.15, -0.70,  0.60, 2.05, -0.30,  0.50,  0.20]
    },
    "rps_paper": {
        "left":  [-0.45, -0.35, -0.30, 0.75,  0.00,  0.20,  0.00],
        "right": [ 0.45, -0.35,  0.30, 0.75,  0.00,  0.20,  0.00]
    },
    "rps_scissors": {
        "left":  [-0.05, -0.55, -0.80, 1.65,  0.50,  0.70,  0.40],
        "right": [ 0.05, -0.55,  0.80, 1.65, -0.50,  0.70, -0.40]
    },

    # Fist bump & High-Five
    "fistbump_ready": {
        "left":  [-0.08, -1.00, -1.19, 1.94,  0.67,  1.03, -0.50],
        "right": [ 0.15, -0.35,  0.10, 0.85,  0.00,  0.00,  0.00]
    },
    "highfive_ready": {
        "left":  [-0.08, -1.00, -1.19, 1.94,  0.67,  1.03, -0.50],
        "right": [ 0.25, -0.55,  0.40, 0.65,  0.00, -0.30,  0.00]
    },

    # Jedi Force Recoil
    "force_recoil": {
        "left":  [-0.50, -0.90, -1.20, 2.20,  0.50,  0.80,  0.00],
        "right": [ 0.50, -0.90,  1.20, 2.20, -0.50,  0.80,  0.00]
    }
}


class InteractiveArena:
    """
    Unified Interactive Playground for Baxter.
    Provides Rock-Paper-Scissors, Reflex Boxer, Jedi Shadow Puppeteering, and Fist-Bumps.
    """

    def __init__(
        self,
        baxter: "Baxter",
        model_path: Optional[str] = None,
        camera_source: Union[int, str] = "auto",
        mirror: bool = True,
        show_gui: bool = True
    ):
        self.baxter = baxter
        self.detector = GestureDetector(model_path)
        self.mirror = mirror
        self.show_gui = show_gui

        # Auto-detect camera: prefer external USB camera (0) if available
        if camera_source == "auto":
            try:
                _test_cap = cv2.VideoCapture(0)
                if _test_cap.isOpened():
                    _ret, _ = _test_cap.read()
                    self.camera_source = 0 if _ret else "head_camera"
                else:
                    self.camera_source = "head_camera"
                _test_cap.release()
            except Exception:
                self.camera_source = "head_camera"
        else:
            self.camera_source = camera_source

        # Available Game Modes:
        # 1: BOXING, 2: RPS, 3: JEDI_MIRROR, 4: BUMP_AND_FIVE
        self.current_mode = 2 # Start with Rock-Paper-Scissors!
        self.mode_names = {
            1: "ARCADE BOXER 2.0",
            2: "ROCK-PAPER-SCISSORS",
            3: "JEDI SHADOW PUPPET",
            4: "HIGH-FIVE & FIST-BUMP"
        }

        # Shared frame buffers
        self.latest_bgr: Optional[np.ndarray] = None
        self.latest_frame_time: float = 0.0
        self.camera_fps: float = 0.0
        self.running: bool = False

        # Motor targets
        self.target_left: List[float] = list(POSES["neutral"]["left"])
        self.target_right: List[float] = list(POSES["neutral"]["right"])
        self.target_head_pan: float = 0.0

        # Jedi mode scene flip configuration (flip horizontally and vertically)
        self.jedi_flip_h = True
        self.jedi_flip_v = True

        # Game State - RPS
        self.rps_phase = "idle" # idle, countdown, shoot, result
        self.rps_count_val = 3
        self.rps_phase_start = 0.0
        self.baxter_rps_choice = "rock"
        self.player_rps_choice = None
        self.rps_player_score = 0
        self.rps_baxter_score = 0
        self.rps_banner = "PRESS [SPACE] TO PLAY ROCK-PAPER-SCISSORS!"

        # Game State - Boxer
        self.box_active_action = "guard"
        self.box_action_until = 0.0
        self.box_blocks = 0
        self.box_jabs = 0
        self.last_action_time = 0.0

        # Game State - Fistbump
        self.bump_state = "ready" # ready, bumping, highfive, return
        self.bump_until = 0.0

        # Teleop filtering
        self.smooth_teleop_l = list(POSES["neutral"]["left"])
        self.smooth_teleop_r = list(POSES["neutral"]["right"])

    async def _camera_receiver(self):
        """Dedicated background task: Ingests frames from external USB camera or Baxter head camera."""
        is_usb = isinstance(self.camera_source, int) or (isinstance(self.camera_source, str) and (self.camera_source.isdigit() or "/dev/video" in self.camera_source))
        if is_usb:
            dev_idx = int(self.camera_source) if str(self.camera_source).isdigit() else self.camera_source
            cap = cv2.VideoCapture(dev_idx)
            if not cap.isOpened():
                self.camera_source = "head_camera"
            else:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                t_fps_start = time.time()
                fps_counter = 0
                loop = asyncio.get_event_loop()

                while self.running:
                    ret, frame = await loop.run_in_executor(None, cap.read)
                    if not ret:
                        await asyncio.sleep(0.01)
                        continue

                    if self.mirror:
                        frame = cv2.flip(frame, 1)

                    self.latest_bgr = frame
                    self.latest_frame_time = time.time()
                    fps_counter += 1

                    now = time.time()
                    if now - t_fps_start >= 1.0:
                        self.camera_fps = fps_counter / (now - t_fps_start)
                        fps_counter = 0
                        t_fps_start = now

                    await asyncio.sleep(0.005)

                cap.release()
                return

        topic = "/cameras/head_camera/image"
        await self.baxter.subscribe(topic)

        t_fps_start = time.time()
        fps_counter = 0

        while self.running and self.baxter.is_connected:
            try:
                raw = await self.baxter.ws.recv()
            except Exception:
                break

            import json
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            if msg.get("topic") == topic:
                m = msg.get("msg", {})
                h, w = m.get("height", 0), m.get("width", 0)
                data_b64 = m.get("data", "")
                if data_b64 and h > 0 and w > 0:
                    raw_bytes = base64.b64decode(data_b64)
                    if len(raw_bytes) == h * w * 4 or "8" in m.get("encoding", ""):
                        frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((h, w, 4))[:, :, :3]
                    elif len(raw_bytes) == h * w * 3:
                        frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((h, w, 3))
                    else:
                        continue

                    # 1. Physical 180° reorientation (fixes upside-down camera mounting)
                    frame = cv2.rotate(frame, cv2.ROTATE_180)

                    # 2. Intuitive Human Mirror Mode (selfie reflection)
                    if self.mirror:
                        frame = cv2.flip(frame, 1)

                    self.latest_bgr = frame
                    self.latest_frame_time = time.time()
                    fps_counter += 1

                    now = time.time()
                    if now - t_fps_start >= 1.0:
                        self.camera_fps = fps_counter / (now - t_fps_start)
                        fps_counter = 0
                        t_fps_start = now

    async def _motor_controller(self):
        """Dedicated 50 Hz background task: Smoothly executes joint commands."""
        cur_left = list(self.target_left)
        cur_right = list(self.target_right)
        alpha = 0.10
        dt = 0.02

        while self.running and self.baxter.is_connected:
            for arm in ("left", "right"):
                await self.baxter.publish(f"/robot/limb/{arm}/suppress_collision_avoidance", {})

            for i in range(7):
                cur_left[i] = alpha * self.target_left[i] + (1.0 - alpha) * cur_left[i]
                cur_right[i] = alpha * self.target_right[i] + (1.0 - alpha) * cur_right[i]

            await self.baxter.publish("/robot/limb/left/joint_command", {
                "mode": 1, "names": JOINTS["left"], "command": cur_left
            })
            await self.baxter.publish("/robot/limb/right/joint_command", {
                "mode": 1, "names": JOINTS["right"], "command": cur_right
            })

            await self.baxter.head.pan(self.target_head_pan, speed_ratio=0.75)
            await asyncio.sleep(dt)

    async def _display_controller(self):
        """Dedicated 2 Hz background task: Updates Baxter's 1024x600 head screen."""
        last_text = ""
        while self.running and self.baxter.is_connected:
            text = f"MODE: {self.mode_names[self.current_mode]}"
            emotion = "happy"

            if self.current_mode == 1: # Boxer
                emotion = "boxing"
                text = f"BOXING | BLOCKS: {self.box_blocks} | JABS: {self.box_jabs}"
            elif self.current_mode == 2: # RPS
                if self.rps_phase == "countdown":
                    text = f"SHOOT IN: {self.rps_count_val}..."
                    emotion = "focused"
                elif self.rps_phase == "shoot":
                    text = f"BAXTER: {self.baxter_rps_choice.upper()}!"
                    emotion = "surprised"
                elif self.rps_phase == "result":
                    text = self.rps_banner
                    emotion = "wink" if "YOU WIN" in self.rps_banner else ("sleepy" if "BAXTER WINS" in self.rps_banner else "happy")
                else:
                    text = f"RPS | YOU: {self.rps_player_score}  BAXTER: {self.rps_baxter_score}"
                    emotion = "happy"
            elif self.current_mode == 3: # Jedi
                emotion = "disco"
                text = "JEDI FORCE TELEOPERATION"
            elif self.current_mode == 4: # Bump
                emotion = "wink"
                text = "HIGH-FIVE & FIST-BUMP!"

            if text != last_text:
                last_text = text
                await self.baxter.display.show_emotion(emotion=emotion, status_text=text)

            await asyncio.sleep(0.4)

    def _draw_arena_hud(
        self,
        frame: np.ndarray,
        fps: float,
        detected_gesture: Optional[str],
        confidence: float
    ) -> np.ndarray:
        """Renders stylized arcade HUD over OpenCV window."""
        h, w = frame.shape[:2]
        out = frame.copy()

        # Top Header Bar
        hdr = out.copy()
        cv2.rectangle(hdr, (0, 0), (w, 55), (15, 12, 22), -1)
        cv2.addWeighted(hdr, 0.78, out, 0.22, 0, out)

        cv2.putText(out, "BAXTER INTERACTIVE ARENA", (14, 26), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 220, 255), 1, cv2.LINE_AA)
        perf = f"FPS: {fps:4.1f} | MIRROR: {'ON' if self.mirror else 'OFF'}"
        cv2.putText(out, perf, (w - 235, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 180), 1, cv2.LINE_AA)

        # Mode Badges
        badge_y = 46
        modes = [(1, "1:BOXER"), (2, "2:RPS"), (3, "3:JEDI"), (4, "4:BUMP")]
        for idx, lbl in modes:
            bx = 14 + (idx - 1) * 115
            is_active = (idx == self.current_mode)
            color = (0, 255, 255) if is_active else (130, 140, 160)
            thick = 2 if is_active else 1
            cv2.putText(out, f"[{lbl}]", (bx, badge_y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, thick, cv2.LINE_AA)

        # Footer Status Bar
        ftr = out.copy()
        cv2.rectangle(ftr, (0, h - 45), (w, h), (15, 12, 22), -1)
        cv2.addWeighted(ftr, 0.78, out, 0.22, 0, out)

        instructions = "[1-4] Mode | [SPACE] Play | [m] Mirror | [q] Exit"
        cv2.putText(out, instructions, (14, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 180, 210), 1, cv2.LINE_AA)

        # Center Action Banner according to mode
        banner_text = ""
        banner_color = (0, 255, 255)

        if self.current_mode == 2: # RPS
            banner_text = self.rps_banner
            if "YOU WIN" in banner_text:
                banner_color = (0, 255, 100)
            elif "BAXTER WINS" in banner_text:
                banner_color = (0, 100, 255)
            elif self.rps_phase == "countdown":
                banner_text = f"GET READY: {self.rps_count_val}..."
                banner_color = (0, 220, 255)

            score_badge = f"SCORE -> YOU: {self.rps_player_score}  |  BAXTER: {self.rps_baxter_score}"
            cv2.putText(out, score_badge, (w - 320, h - 16), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        elif self.current_mode == 1: # Boxer
            banner_text = f"BOXING: {self.box_active_action.upper()}"
            banner_color = (0, 80, 255) if "BLOCK" in banner_text else ((0, 255, 120) if "JAB" in banner_text else (255, 200, 0))
            score_badge = f"BLOCKS: {self.box_blocks}  |  JABS: {self.box_jabs}"
            cv2.putText(out, score_badge, (w - 280, h - 16), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        elif self.current_mode == 3: # Jedi
            banner_text = "JEDI SHADOW PUPPET: MOVE BOTH HANDS"
            banner_color = (255, 0, 220)
            flip_parts = []
            if self.jedi_flip_h: flip_parts.append("H")
            if self.jedi_flip_v: flip_parts.append("V")
            flip_str = "+".join(flip_parts) if flip_parts else "OFF"
            cv2.putText(out, f"FLIP: {flip_str} ([m]/[v])", (w - 240, h - 16), cv2.FONT_HERSHEY_DUPLEX, 0.55, (0, 255, 200), 1, cv2.LINE_AA)

        elif self.current_mode == 4: # Bump
            banner_text = "HOLD OUT A FIST OR RAISE HIGH-FIVE!"
            banner_color = (0, 200, 255)

        if banner_text:
            tsz = cv2.getTextSize(banner_text, cv2.FONT_HERSHEY_DUPLEX, 0.65, 2)[0]
            cx = (w - tsz[0]) // 2
            pill = out.copy()
            cv2.rectangle(pill, (cx - 10, 68), (cx + tsz[0] + 10, 96), (20, 16, 28), -1)
            cv2.addWeighted(pill, 0.70, out, 0.30, 0, out)
            cv2.rectangle(out, (cx - 10, 68), (cx + tsz[0] + 10, 96), banner_color, 2)
            cv2.putText(out, banner_text, (cx, 90), cv2.FONT_HERSHEY_DUPLEX, 0.65, banner_color, 2, cv2.LINE_AA)

        # Detected Gesture Pill
        if detected_gesture and detected_gesture != "None":
            badge = f"HAND: {detected_gesture.upper()} ({confidence*100:.0f}%)"
            cv2.putText(out, badge, (14, 125), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        return out

    # -------------------------------------------------------------------------
    # Game Logic 1: Rock-Paper-Scissors
    # -------------------------------------------------------------------------
    def _trigger_rps_round(self):
        """Starts a new Rock-Paper-Scissors countdown round."""
        self.rps_phase = "countdown"
        self.rps_count_val = 3
        self.rps_phase_start = time.time()
        self.player_rps_choice = None
        self.baxter_rps_choice = random.choice(["rock", "paper", "scissors"])
        play_sound("beep")
        self.target_left = list(ARENA_POSES["rps_pump"]["left"])
        self.target_right = list(ARENA_POSES["rps_pump"]["right"])

    def _update_rps_game(self, now: float, detected_gesture: Optional[str], confidence: float):
        """State machine for Rock-Paper-Scissors."""
        if self.rps_phase == "countdown":
            elapsed = now - self.rps_phase_start
            if elapsed < 0.6:
                self.rps_count_val = 3
                self.target_left = list(ARENA_POSES["rps_pump"]["left"])
                self.target_right = list(ARENA_POSES["rps_pump"]["right"])
            elif elapsed < 1.2:
                if self.rps_count_val != 2:
                    self.rps_count_val = 2
                    play_sound("beep")
                self.target_left = list(ARENA_POSES["rps_ready"]["left"])
                self.target_right = list(ARENA_POSES["rps_ready"]["right"])
            elif elapsed < 1.8:
                if self.rps_count_val != 1:
                    self.rps_count_val = 1
                    play_sound("beep")
                self.target_left = list(ARENA_POSES["rps_pump"]["left"])
                self.target_right = list(ARENA_POSES["rps_pump"]["right"])
            else:
                # SHOOT!
                self.rps_phase = "shoot"
                self.rps_phase_start = now
                play_sound("shoot")

                # Baxter executes its choice
                if self.baxter_rps_choice == "rock":
                    self.target_left = list(ARENA_POSES["rps_rock"]["left"])
                    self.target_right = list(ARENA_POSES["rps_rock"]["right"])
                elif self.baxter_rps_choice == "paper":
                    self.target_left = list(ARENA_POSES["rps_paper"]["left"])
                    self.target_right = list(ARENA_POSES["rps_paper"]["right"])
                else: # scissors
                    self.target_left = list(ARENA_POSES["rps_scissors"]["left"])
                    self.target_right = list(ARENA_POSES["rps_scissors"]["right"])

        elif self.rps_phase == "shoot":
            # Detect player hand choice within 1.2s window
            if detected_gesture == "Closed_Fist" and confidence > 0.5:
                self.player_rps_choice = "rock"
            elif detected_gesture == "Open_Palm" and confidence > 0.5:
                self.player_rps_choice = "paper"
            elif detected_gesture in ("Victory", "Pointing_Up") and confidence > 0.5:
                self.player_rps_choice = "scissors"

            if now - self.rps_phase_start > 1.2 or self.player_rps_choice is not None:
                self.rps_phase = "result"
                self.rps_phase_start = now

                # Evaluate winner
                p = self.player_rps_choice
                b = self.baxter_rps_choice

                if not p:
                    self.rps_banner = f"NO HAND DETECTED! BAXTER PLAYED {b.upper()}!"
                    play_sound("fail")
                elif p == b:
                    self.rps_banner = f"TIE GAME! BOTH PLAYED {p.upper()}!"
                    play_sound("whoosh")
                elif (p == "rock" and b == "scissors") or (p == "paper" and b == "rock") or (p == "scissors" and b == "paper"):
                    self.rps_banner = f"🎉 YOU WIN! {p.upper()} BEATS {b.upper()}! 🎉"
                    self.rps_player_score += 1
                    play_sound("cheer")
                else:
                    self.rps_banner = f"🤖 BAXTER WINS! {b.upper()} BEATS {p.upper()}!"
                    self.rps_baxter_score += 1
                    play_sound("fail")

        elif self.rps_phase == "result":
            if now - self.rps_phase_start > 3.0:
                self.rps_phase = "idle"
                self.rps_banner = "ROUND OVER! PRESS [SPACE] TO PLAY AGAIN!"
                self.target_left = list(ARENA_POSES["rps_ready"]["left"])
                self.target_right = list(ARENA_POSES["rps_ready"]["right"])

    # -------------------------------------------------------------------------
    # Game Logic 2: Arcade Reflex Boxer
    # -------------------------------------------------------------------------
    def _update_boxer(self, now: float, detected_gesture: Optional[str], confidence: float, hand_x: float):
        """Processes boxing triggers with audio and combo feedback."""
        boxing_poses = POSES["boxing"]

        # Smooth head tracking
        target_pan = float(np.clip((0.5 - hand_x) * 1.5, -0.65, 0.65))
        self.target_head_pan = target_pan

        if now > self.box_action_until and now - self.last_action_time > 0.7:
            if detected_gesture == "Closed_Fist" and confidence >= 0.52:
                # Slip & Parrying Block
                self.box_blocks += 1
                self.last_action_time = now
                self.box_action_until = now + 1.1
                play_sound("whoosh")

                if hand_x < 0.5:
                    self.box_active_action = "block_right"
                    self.target_right = list(boxing_poses["block_right"]["right"])
                    self.target_left = list(boxing_poses["guard"]["left"])
                else:
                    self.box_active_action = "block_left"
                    self.target_left = list(boxing_poses["block_left"]["left"])
                    self.target_right = list(boxing_poses["guard"]["right"])

            elif detected_gesture == "Open_Palm" and confidence >= 0.52:
                # Fast Target Jab
                self.box_jabs += 1
                self.last_action_time = now
                self.box_action_until = now + 1.1
                play_sound("punch")

                if hand_x < 0.5:
                    self.box_active_action = "jab_right"
                    self.target_right = list(boxing_poses["jab_right"]["right"])
                    self.target_left = list(boxing_poses["guard"]["left"])
                else:
                    self.box_active_action = "jab_left"
                    self.target_left = list(boxing_poses["jab_left"]["left"])
                    self.target_right = list(boxing_poses["guard"]["right"])

            elif detected_gesture in ("Thumb_Up", "Victory") and confidence >= 0.52:
                self.last_action_time = now
                self.box_action_until = now + 2.0
                self.box_active_action = "celebrate"
                play_sound("cheer")
                self.target_left = list(POSES["cheer"]["left"])
                self.target_right = list(POSES["cheer"]["right"])

        if now > self.box_action_until and self.box_active_action != "guard":
            self.box_active_action = "guard"
            self.target_left = list(boxing_poses["guard"]["left"])
            self.target_right = list(boxing_poses["guard"]["right"])

    # -------------------------------------------------------------------------
    # Game Logic 3: Jedi Shadow Puppeteer / Teleoperation
    # -------------------------------------------------------------------------
    def _update_jedi_mirror(self, detections: List[Dict]):
        """Maps player's hand positions directly to Baxter's dual arm angles."""
        if not detections:
            return

        for det in detections:
            hx, hy = det["wrist"]
            gesture = det["gesture"]

            # Check for Jedi Force Push (push forward with open palm)
            if gesture == "Open_Palm" and hy < 0.35:
                play_sound("whoosh")
                self.target_left = list(ARENA_POSES["force_recoil"]["left"])
                self.target_right = list(ARENA_POSES["force_recoil"]["right"])
                return

            # Map wrist X & Y to shoulder and elbow angles
            # Y normalized [0..1] -> shoulder pitch s1 [-1.5 to -0.3 rad]
            s1_val = float(np.clip(-1.6 + (1.0 - hy) * 1.4, -1.8, -0.3))
            # Elbow bend e1
            e1_val = float(np.clip(0.8 + hy * 1.2, 0.6, 2.0))

            if hx < 0.5:
                # User's left (facing Baxter's right arm)
                # s0 > 0 rolls Baxter's right arm outward to the user's left
                s0_right = float(np.clip((0.5 - hx) * 1.8, -0.2, 0.9))
                self.target_right = [s0_right, s1_val, 0.80, e1_val, -0.20, 0.80, 0.0]
            else:
                # User's right (facing Baxter's left arm)
                # s0 < 0 rolls Baxter's left arm outward to the user's right
                s0_left = float(np.clip(-(hx - 0.5) * 1.8, -0.9, 0.2))
                self.target_left = [s0_left, s1_val, -0.80, e1_val, 0.20, 0.80, 0.0]

    # -------------------------------------------------------------------------
    # Game Logic 4: Fist-Bump & High-Five
    # -------------------------------------------------------------------------
    def _update_bump_and_five(self, now: float, detected_gesture: Optional[str], confidence: float):
        """Interactive physical greeting state machine."""
        if now < self.bump_until:
            return

        if detected_gesture == "Closed_Fist" and confidence >= 0.55:
            # Fist Bump
            play_sound("fistbump")
            self.bump_until = now + 2.2
            self.target_right = list(ARENA_POSES["fistbump_ready"]["right"])
            self.target_left = list(ARENA_POSES["fistbump_ready"]["left"])
            asyncio.create_task(self.baxter.head.nod())

        elif detected_gesture == "Open_Palm" and confidence >= 0.55:
            # High Five
            play_sound("highfive")
            self.bump_until = now + 2.2
            self.target_right = list(ARENA_POSES["highfive_ready"]["right"])
            self.target_left = list(ARENA_POSES["highfive_ready"]["left"])
            asyncio.create_task(self.baxter.head.nod())

        else:
            # Return to neutral waiting pose
            self.target_right = list(POSES["neutral"]["right"])
            self.target_left = list(POSES["neutral"]["left"])

    # -------------------------------------------------------------------------
    # Main Execution Loop
    # -------------------------------------------------------------------------
    async def run(self, duration_sec: float = 300.0):
        """Runs the interactive arena."""
        print("=" * 70)
        print("       🎮 BAXTER INTERACTIVE ARENA - HRI PLAYGROUND 🎮")
        print("=" * 70)
        print("  Hotkeys:")
        print("    [1] Arcade Reflex Boxer 2.0 (Combos & Parrying)")
        print("    [2] Rock-Paper-Scissors Showdown (Play with Spacebar)")
        print("    [3] Jedi Shadow Puppeteer (Live Hand Teleoperation)")
        print("    [4] Interactive High-Five & Fist-Bump Partner")
        print("    [m] Toggle Selfie Mirror Mode (ON / OFF)")
        print("    [q] Exit Arena and return Baxter to neutral posture\n")

        state = await self.baxter.get_state()
        if not state.get("enabled"):
            print("[*] Powering on Baxter motors...")
            await self.baxter.enable()

        self.running = True
        play_sound("ding")

        # Launch background tasks
        cam_task = asyncio.create_task(self._camera_receiver())
        motor_task = asyncio.create_task(self._motor_controller())
        disp_task = asyncio.create_task(self._display_controller())

        print("[*] Connecting to Baxter head camera feed...")
        t_wait = time.time()
        while self.latest_bgr is None and time.time() - t_wait < 6.0:
            await asyncio.sleep(0.05)

        if self.latest_bgr is None:
            print("[!] Failed to acquire camera stream. Exiting.")
            self.running = False
            return

        win_name = "Baxter Interactive Arena | Live Vision Playground"
        if self.show_gui:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(win_name, 720, 480)

        t_start = time.time()
        print("[✓] Arena is LIVE! Step in front of Baxter and have fun!\n")

        try:
            while self.running:
                now = time.time()
                if now - t_start > duration_sec:
                    break

                if self.latest_bgr is None:
                    await asyncio.sleep(0.02)
                    continue

                frame = self.latest_bgr.copy()

                # For Jedi mode: flip scene horizontally and vertically
                if self.current_mode == 3:
                    if self.jedi_flip_h and self.jedi_flip_v:
                        frame = cv2.flip(frame, -1)
                    elif self.jedi_flip_h:
                        frame = cv2.flip(frame, 1)
                    elif self.jedi_flip_v:
                        frame = cv2.flip(frame, 0)

                # Run MediaPipe hand detection
                detections = self.detector.detect(frame)
                top_gesture = None
                top_confidence = 0.0
                hand_x = 0.5

                if detections:
                    top = detections[0]
                    top_gesture = top["gesture"]
                    top_confidence = top["score"]
                    hand_x = top["wrist"][0]

                    # Draw colorful skeletal joints
                    for det in detections:
                        if det.get("landmarks"):
                            color = (0, 80, 255) if top_gesture == "Closed_Fist" else (
                                (0, 255, 120) if top_gesture == "Open_Palm" else (0, 220, 255)
                            )
                            draw_hand_skeleton(frame, det["landmarks"], color=color)

                # Process active mode state machine
                if self.current_mode == 1:
                    self._update_boxer(now, top_gesture, top_confidence, hand_x)
                elif self.current_mode == 2:
                    self._update_rps_game(now, top_gesture, top_confidence)
                elif self.current_mode == 3:
                    self._update_jedi_mirror(detections)
                elif self.current_mode == 4:
                    self._update_bump_and_five(now, top_gesture, top_confidence)

                # Render HUD
                hud = self._draw_arena_hud(
                    frame=frame,
                    fps=self.camera_fps,
                    detected_gesture=top_gesture,
                    confidence=top_confidence
                )

                if self.show_gui:
                    cv2.imshow(win_name, hud)
                    key = cv2.waitKey(1) & 0xFF

                    if key in (ord('q'), 27):
                        print("[*] Exit key pressed. Wrapping up Arena session...")
                        break
                    elif key == ord('1'):
                        self.current_mode = 1
                        play_sound("ding")
                        print("[*] Mode switched to: 🥊 ARCADE BOXER 2.0")
                    elif key == ord('2'):
                        self.current_mode = 2
                        play_sound("ding")
                        print("[*] Mode switched to: 🎮 ROCK-PAPER-SCISSORS")
                    elif key == ord('3'):
                        self.current_mode = 3
                        play_sound("whoosh")
                        print("[*] Mode switched to: 🪄 JEDI SHADOW PUPPETEER (Scene flipped H+V)")
                        print("    Hotkeys: [m] Toggle Horizontal Flip | [v] Toggle Vertical Flip | [f] Toggle Both")
                    elif key == ord('4'):
                        self.current_mode = 4
                        play_sound("ding")
                        print("[*] Mode switched to: 🤝 HIGH-FIVE & FIST-BUMP")
                    elif key == ord(' '):
                        if self.current_mode == 2:
                            self._trigger_rps_round()
                    elif key == ord('m'):
                        if self.current_mode == 3:
                            self.jedi_flip_h = not self.jedi_flip_h
                            print(f"[*] Jedi horizontal flip: {'ON' if self.jedi_flip_h else 'OFF'}")
                        else:
                            self.mirror = not self.mirror
                            print(f"[*] Mirror mode: {'ON' if self.mirror else 'OFF'}")
                    elif key == ord('v'):
                        self.jedi_flip_v = not self.jedi_flip_v
                        print(f"[*] Jedi vertical flip: {'ON' if self.jedi_flip_v else 'OFF'}")
                    elif key == ord('f'):
                        both = not (self.jedi_flip_h and self.jedi_flip_v)
                        self.jedi_flip_h = both
                        self.jedi_flip_v = both
                        print(f"[*] Jedi full flip (H+V): {'ON' if both else 'OFF'}")

                await asyncio.sleep(0.015)

        finally:
            self.running = False
            cam_task.cancel()
            motor_task.cancel()
            disp_task.cancel()
            await asyncio.gather(cam_task, motor_task, disp_task, return_exceptions=True)

            try:
                await self.baxter.unsubscribe("/cameras/head_camera/image")
            except Exception:
                pass
            await asyncio.sleep(0.15)

            if self.show_gui:
                cv2.destroyAllWindows()

            print("\n[*] Returning Baxter limbs to neutral posture...")
            await self.baxter.untuck(duration=3.0)
            await self.baxter.display.show_emotion("happy", status_text="THANKS FOR PLAYING!")
            print("[✓] Arena session cleanly closed.")
