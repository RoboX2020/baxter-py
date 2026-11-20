"""
Baxter Vision & AI - Real-Time MediaPipe Hand Tracking and Interactive Boxing Sparring.
Features zero-latency decoupled camera ingestion, live OpenCV HUD feed, and diagnostic logging.
"""

import os
import sys
import time
import math
import base64
import asyncio
from typing import Optional, Tuple, List, Dict
import numpy as np
import cv2

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False

from .poses import JOINTS, POSES
from .display import Display, WIDTH as DISP_W, HEIGHT as DISP_H

DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
DEFAULT_MODEL_PATH = os.path.join(DEFAULT_MODEL_DIR, "gesture_recognizer.task")

# Skeletal connections between the 21 MediaPipe hand landmarks
HAND_CONNECTIONS = [
    # Thumb
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Index
    (0, 5), (5, 6), (6, 7), (7, 8),
    # Middle
    (5, 9), (9, 10), (10, 11), (11, 12),
    # Ring
    (9, 13), (13, 14), (14, 15), (15, 16),
    # Pinky
    (13, 17), (17, 18), (18, 19), (19, 20),
    # Palm base
    (0, 17)
]


class GestureDetector:
    """Wrapper around MediaPipe Gesture Recognizer with landmark extraction."""

    def __init__(self, model_path: Optional[str] = None):
        if not HAS_MEDIAPIPE:
            raise ImportError("MediaPipe is required for vision features. Install with 'pip install mediapipe'.")

        self.model_path = model_path or DEFAULT_MODEL_PATH
        if not os.path.exists(self.model_path):
            fallback = "/home/robotics/models/gesture_recognizer.task"
            if os.path.exists(fallback):
                self.model_path = fallback
            else:
                raise FileNotFoundError(f"Gesture recognizer model not found at {self.model_path}")

        base_options = mp_python.BaseOptions(model_asset_path=self.model_path)
        options = mp_vision.GestureRecognizerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=0.50,
            min_hand_presence_confidence=0.50,
            min_tracking_confidence=0.50
        )
        self.recognizer = mp_vision.GestureRecognizer.create_from_options(options)

    def detect(self, bgr_frame: np.ndarray) -> List[Dict]:
        """
        Runs gesture recognition on BGR image.
        Returns list of detected hands with 'gesture', 'score', 'wrist', and 'landmarks'.
        """
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.recognizer.recognize(mp_image)

        detections = []
        if result.gestures:
            for i, gesture_list in enumerate(result.gestures):
                if not gesture_list:
                    continue
                top = gesture_list[0]
                wrist = (0.5, 0.5)
                norm_landmarks = []

                if result.hand_landmarks and i < len(result.hand_landmarks):
                    raw_lms = result.hand_landmarks[i]
                    wrist = (raw_lms[0].x, raw_lms[0].y)
                    norm_landmarks = [(lm.x, lm.y) for lm in raw_lms]

                detections.append({
                    "gesture": top.category_name,
                    "score": top.score,
                    "wrist": wrist,
                    "landmarks": norm_landmarks
                })
        return detections


def draw_hand_skeleton(frame: np.ndarray, landmarks: List[Tuple[float, float]], color: Tuple[int, int, int] = (0, 255, 200)):
    """Draws anti-aliased hand skeleton and joint landmarks on OpenCV frame."""
    h, w = frame.shape[:2]
    pts = [(int(x * w), int(y * h)) for (x, y) in landmarks]

    # Draw bone connections
    for p1_idx, p2_idx in HAND_CONNECTIONS:
        if p1_idx < len(pts) and p2_idx < len(pts):
            cv2.line(frame, pts[p1_idx], pts[p2_idx], color, 2, cv2.LINE_AA)

    # Draw joint dots
    for i, pt in enumerate(pts):
        joint_color = (0, 180, 255) if i in (4, 8, 12, 16, 20) else (255, 255, 255)
        radius = 5 if i in (0, 4, 8, 12, 16, 20) else 3
        cv2.circle(frame, pt, radius, joint_color, -1, cv2.LINE_AA)
        cv2.circle(frame, pt, radius + 1, (0, 0, 0), 1, cv2.LINE_AA)


def draw_boxing_hud(
    frame: np.ndarray,
    fps: float,
    latency_ms: float,
    gesture_name: Optional[str],
    confidence: float,
    active_mode: str,
    hits: int,
    blocks: int,
    round_sec: float
) -> np.ndarray:
    """Renders real-time HUD with status telemetry, action banners, and scorecard."""
    h, w = frame.shape[:2]
    out = frame.copy()

    # 1. Semi-transparent header banner
    header_overlay = out.copy()
    cv2.rectangle(header_overlay, (0, 0), (w, 42), (18, 14, 24), -1)
    cv2.addWeighted(header_overlay, 0.75, out, 0.25, 0, out)

    # Title & Telemetry
    cv2.putText(out, "BAXTER BOXING AI | LIVE VISION FEED", (12, 26), cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 220, 255), 1, cv2.LINE_AA)
    perf_text = f"FPS: {fps:4.1f} | Latency: {latency_ms:3.0f}ms"
    cv2.putText(out, perf_text, (w - 230, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 180), 1, cv2.LINE_AA)

    # 2. Semi-transparent footer banner
    footer_overlay = out.copy()
    cv2.rectangle(footer_overlay, (0, h - 38), (w, h), (18, 14, 24), -1)
    cv2.addWeighted(footer_overlay, 0.75, out, 0.25, 0, out)

    # Bottom Instructions & Round Timer
    round_str = f"ROUND: {int(max(0, round_sec))}s"
    cv2.putText(out, round_str, (12, h - 14), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 200, 0), 1, cv2.LINE_AA)
    score_str = f"JABS: {hits}  |  BLOCKS: {blocks}"
    cv2.putText(out, score_str, (170, h - 14), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(out, "[q/ESC] Exit | [r] Reset | [g] Guard", (w - 260, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1, cv2.LINE_AA)

    # 3. Action Mode Banner (Center Top)
    mode_color = (0, 200, 255) # Default cyan
    mode_label = active_mode.upper().replace("_", " ")

    if "BLOCK" in active_mode:
        mode_color = (0, 80, 255) # Red / Orange
        mode_label = f"SHIELD UP: {mode_label}"
    elif "JAB" in active_mode:
        mode_color = (0, 255, 100) # Bright Green
        mode_label = f"FAST STRIKE: {mode_label}"
    elif "CELEBRATE" in active_mode:
        mode_color = (0, 220, 255) # Yellow / Gold
        mode_label = "CHAMPIONSHIP CELEBRATION!"
    elif active_mode == "guard":
        mode_color = (255, 200, 0) # Gold / Cyan
        mode_label = "PEEK-A-BOO GUARD READY"

    # Action Banner pill
    text_size = cv2.getTextSize(mode_label, cv2.FONT_HERSHEY_DUPLEX, 0.7, 2)[0]
    bx = (w - text_size[0]) // 2
    by = 75

    pill_overlay = out.copy()
    cv2.rectangle(pill_overlay, (bx - 12, by - 22), (bx + text_size[0] + 12, by + 8), (20, 16, 28), -1)
    cv2.addWeighted(pill_overlay, 0.70, out, 0.30, 0, out)
    cv2.rectangle(out, (bx - 12, by - 22), (bx + text_size[0] + 12, by + 8), mode_color, 2)
    cv2.putText(out, mode_label, (bx, by), cv2.FONT_HERSHEY_DUPLEX, 0.7, mode_color, 2, cv2.LINE_AA)

    # 4. Detected Gesture Badge
    if gesture_name and gesture_name != "None":
        badge_text = f"DETECTED: {gesture_name.upper()} ({confidence*100:.0f}%)"
        cv2.putText(out, badge_text, (15, 110), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    return out


class BoxerSparring:
    """
    High-Performance Interactive Boxing AI Partner.
    Decouples camera ingestion, 50 Hz motor control, and MediaPipe inference for zero latency.
    """

    def __init__(
        self,
        baxter: "Baxter",
        model_path: Optional[str] = None,
        show_gui: bool = True,
        verbose: bool = True
    ):
        self.baxter = baxter
        self.detector = GestureDetector(model_path)
        self.show_gui = show_gui
        self.verbose = verbose

        # Shared state buffers
        self.latest_bgr: Optional[np.ndarray] = None
        self.latest_frame_time: float = 0.0
        self.camera_fps: float = 0.0
        self.frame_count: int = 0
        self.running: bool = False

        # Motor targets
        self.boxing_poses = POSES["boxing"]
        self.target_left: List[float] = list(self.boxing_poses["guard"]["left"])
        self.target_right: List[float] = list(self.boxing_poses["guard"]["right"])
        self.target_head_pan: float = 0.0

        # Sparring scoring & states
        self.active_mode = "guard"
        self.hits_count = 0
        self.blocks_count = 0
        self.action_until = 0.0
        self.last_action_trigger = 0.0

    def _log(self, tag: str, msg: str):
        if self.verbose:
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] [{tag}] {msg}")

    async def _camera_receiver(self):
        """Dedicated background task: Reads camera frames from WebSocket without blocking."""
        topic = "/cameras/head_camera/image"
        await self.baxter.subscribe(topic)
        self._log("CAMERA", "Subscribed to /cameras/head_camera/image. Starting frame ingestion...")

        t_fps_start = time.time()
        fps_counter = 0

        while self.running and self.baxter.is_connected:
            try:
                raw = await self.baxter.ws.recv()
            except Exception as e:
                if self.running:
                    self._log("CAMERA", f"Receive error: {e}")
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
                    if len(raw_bytes) == h * w * 4:
                        frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((h, w, 4))[:, :, :3]
                    elif len(raw_bytes) == h * w * 3:
                        frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((h, w, 3))
                    else:
                        continue

                    self.latest_bgr = frame
                    self.latest_frame_time = time.time()
                    self.frame_count += 1
                    fps_counter += 1

                    # Measure camera FPS every second
                    now = time.time()
                    if now - t_fps_start >= 1.0:
                        self.camera_fps = fps_counter / (now - t_fps_start)
                        fps_counter = 0
                        t_fps_start = now

    async def _motor_controller(self):
        """Dedicated background task: Streams 50 Hz joint commands to Baxter smoothly."""
        self._log("MOTORS", "Starting 50 Hz non-blocking trajectory loop...")

        # Initialize current commands to guard pose
        cur_left = list(self.target_left)
        cur_right = list(self.target_right)

        alpha = 0.08 # Responsive filter coefficient
        dt = 0.02 # 50 Hz

        while self.running and self.baxter.is_connected:
            # 1. Suppress collision avoidance
            for arm in ("left", "right"):
                await self.baxter.publish(f"/robot/limb/{arm}/suppress_collision_avoidance", {})

            # 2. Filter commands towards targets
            for i in range(7):
                cur_left[i] = alpha * self.target_left[i] + (1.0 - alpha) * cur_left[i]
                cur_right[i] = alpha * self.target_right[i] + (1.0 - alpha) * cur_right[i]

            # 3. Publish joint commands
            await self.baxter.publish("/robot/limb/left/joint_command", {
                "mode": 1,
                "names": JOINTS["left"],
                "command": cur_left
            })
            await self.baxter.publish("/robot/limb/right/joint_command", {
                "mode": 1,
                "names": JOINTS["right"],
                "command": cur_right
            })

            # 4. Pan head smoothly
            await self.baxter.head.pan(self.target_head_pan, speed_ratio=0.7)

            await asyncio.sleep(dt)

    async def _display_updater(self):
        """Dedicated background task: Updates Baxter LCD screen at low rate (2 Hz) to save bandwidth."""
        self._log("DISPLAY", "Starting low-bandwidth LCD screen updater (2 Hz)...")
        last_mode = None
        while self.running and self.baxter.is_connected:
            if self.active_mode != last_mode:
                last_mode = self.active_mode
                emotion = "boxing" if "block" in self.active_mode or "jab" in self.active_mode else (
                    "happy" if self.active_mode == "celebrate" else "focused"
                )
                status = f"MODE: {self.active_mode.upper()} | BLOCKS: {self.blocks_count} | JABS: {self.hits_count}"
                await self.baxter.display.show_emotion(emotion=emotion, status_text=status)

            await asyncio.sleep(0.5)

    async def run(self, duration_sec: float = 60.0):
        """Runs the interactive sparring session with live feed and diagnostic logs."""
        print("=" * 70)
        print("       🥊 BAXTER INTERACTIVE BOXING SPARRING PIPELINE 🥊")
        print("=" * 70)
        print("  • Punch (Closed Fist)  --> Baxter slips and raises high guard block")
        print("  • Pad (Open Palm)      --> Baxter throws straight target jab")
        print("  • Thumbs Up / Victory  --> Baxter celebrates championship victory")
        print("  • Hand Motion          --> Dynamic head and gaze tracking")
        print("  • Press 'q' or ESC in vision window (or Ctrl+C) to finish round.\n")

        # Verify motors enabled
        state = await self.baxter.get_state()
        if not state.get("enabled"):
            self._log("SYSTEM", "Enabling Baxter motors...")
            await self.baxter.enable()

        self.running = True
        self.action_until = 0.0
        self.last_action_trigger = 0.0
        self.hits_count = 0
        self.blocks_count = 0

        # Launch background tasks
        cam_task = asyncio.create_task(self._camera_receiver())
        motor_task = asyncio.create_task(self._motor_controller())
        disp_task = asyncio.create_task(self._display_updater())

        # Wait for first camera frame
        self._log("SYSTEM", "Waiting for live camera frame from Baxter head camera...")
        t_wait = time.time()
        while self.latest_bgr is None and time.time() - t_wait < 5.0:
            await asyncio.sleep(0.05)

        if self.latest_bgr is None:
            self._log("ERROR", "Timed out waiting for camera frames. Aborting.")
            self.running = False
            return

        self._log("SYSTEM", f"Live camera feed acquired! Initial frame: {self.latest_bgr.shape[1]}x{self.latest_bgr.shape[0]}")

        # Setup GUI window if requested
        win_name = "Baxter Boxing Sparring AI | Live Vision Feed"
        if self.show_gui:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(win_name, 720, 480)

        t_round_start = time.time()
        inference_fps = 0.0
        frame_idx = 0
        last_inf_time = time.time()

        try:
            while self.running:
                now = time.time()
                elapsed = now - t_round_start
                remaining = duration_sec - elapsed

                if elapsed >= duration_sec:
                    self._log("SPARRING", f"Round duration completed ({duration_sec:.0f}s). Bell rings! 🔔")
                    break

                if self.latest_bgr is None:
                    await asyncio.sleep(0.02)
                    continue

                # Grab latest frame atomically
                frame = self.latest_bgr.copy()
                frame_ts = self.latest_frame_time
                latency_ms = (now - frame_ts) * 1000.0

                # Run MediaPipe Detection
                t0 = time.time()
                detections = self.detector.detect(frame)
                dt_inf = time.time() - t0

                frame_idx += 1
                if time.time() - last_inf_time >= 0.5:
                    inference_fps = 1.0 / max(0.001, dt_inf)
                    last_inf_time = time.time()

                top_gesture = None
                top_confidence = 0.0
                hand_x, hand_y = 0.5, 0.5

                if detections:
                    det = detections[0]
                    top_gesture = det["gesture"]
                    top_confidence = det["score"]
                    hand_x, hand_y = det["wrist"]

                    # Draw hand skeleton
                    if det.get("landmarks"):
                        skeleton_color = (0, 80, 255) if top_gesture == "Closed_Fist" else (
                            (0, 255, 120) if top_gesture == "Open_Palm" else (0, 220, 255)
                        )
                        draw_hand_skeleton(frame, det["landmarks"], color=skeleton_color)

                    # Dynamic head tracking: Baxter mirrors hand location
                    self.target_head_pan = float(np.clip((0.5 - hand_x) * 1.5, -0.65, 0.65))

                    # State machine triggers
                    if now > self.action_until and now - self.last_action_trigger > 0.75:
                        if top_gesture == "Closed_Fist" and top_confidence >= 0.52:
                            # Opponent throws punch: slip & high block
                            self.blocks_count += 1
                            self.last_action_trigger = now
                            self.action_until = now + 1.2
                            if hand_x < 0.5:
                                self.active_mode = "block_right"
                                self.target_right = list(self.boxing_poses["block_right"]["right"])
                                self.target_left = list(self.boxing_poses["guard"]["left"])
                                self._log("ACTION", f"💥 PUNCH INCOMING -> SLIP & BLOCK RIGHT! (conf: {top_confidence:.2f})")
                            else:
                                self.active_mode = "block_left"
                                self.target_left = list(self.boxing_poses["block_left"]["left"])
                                self.target_right = list(self.boxing_poses["guard"]["right"])
                                self._log("ACTION", f"💥 PUNCH INCOMING -> SLIP & BLOCK LEFT! (conf: {top_confidence:.2f})")

                        elif top_gesture == "Open_Palm" and top_confidence >= 0.52:
                            # Opponent holds up pad: target jab
                            self.hits_count += 1
                            self.last_action_trigger = now
                            self.action_until = now + 1.2
                            if hand_x < 0.5:
                                self.active_mode = "jab_right"
                                self.target_right = list(self.boxing_poses["jab_right"]["right"])
                                self.target_left = list(self.boxing_poses["guard"]["left"])
                                self._log("ACTION", f"🎯 PAD SPOTTED -> STRAIGHT RIGHT JAB! (conf: {top_confidence:.2f})")
                            else:
                                self.active_mode = "jab_left"
                                self.target_left = list(self.boxing_poses["jab_left"]["left"])
                                self.target_right = list(self.boxing_poses["guard"]["right"])
                                self._log("ACTION", f"🎯 PAD SPOTTED -> STRAIGHT LEFT JAB! (conf: {top_confidence:.2f})")

                        elif top_gesture in ("Thumb_Up", "Victory") and top_confidence >= 0.52:
                            self.last_action_trigger = now
                            self.action_until = now + 2.0
                            self.active_mode = "celebrate"
                            self.target_left = list(POSES["cheer"]["left"])
                            self.target_right = list(POSES["cheer"]["right"])
                            self._log("ACTION", f"🏆 VICTORY GESTURE -> CELEBRATING CHAMPIONSHIP!")

                # Return to peek-a-boo guard stance when action duration expires
                if now > self.action_until and self.active_mode != "guard":
                    self.active_mode = "guard"
                    self.target_left = list(self.boxing_poses["guard"]["left"])
                    self.target_right = list(self.boxing_poses["guard"]["right"])
                    self._log("ACTION", "Returning to Peek-a-boo Guard Stance.")

                # Draw Live HUD
                hud_frame = draw_boxing_hud(
                    frame=frame,
                    fps=self.camera_fps or inference_fps,
                    latency_ms=latency_ms,
                    gesture_name=top_gesture,
                    confidence=top_confidence,
                    active_mode=self.active_mode,
                    hits=self.hits_count,
                    blocks=self.blocks_count,
                    round_sec=remaining
                )

                # Render GUI Window
                if self.show_gui:
                    cv2.imshow(win_name, hud_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord('q'), 27): # 'q' or ESC
                        self._log("SPARRING", "User pressed exit key. Ending round.")
                        break
                    elif key == ord('r'):
                        self.hits_count = 0
                        self.blocks_count = 0
                        self._log("SPARRING", "Scorecard reset.")
                    elif key == ord('g'):
                        self.active_mode = "guard"
                        self.target_left = list(self.boxing_poses["guard"]["left"])
                        self.target_right = list(self.boxing_poses["guard"]["right"])

                # Yield briefly to asyncio event loop
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

            self._log("SYSTEM", "Sparring finished. Returning Baxter arms to neutral posture...")
            await self.baxter.untuck(duration=3.0)
            await self.baxter.display.show_emotion("happy", status_text=f"FINAL SCORE - BLOCKS: {self.blocks_count} | JABS: {self.hits_count}")

            print("\n" + "=" * 65)
            print("                 🥊 SPARRING MATCH RESULTS 🥊")
            print("=" * 65)
            print(f"  • Total Sparring Time: {min(duration_sec, time.time() - t_round_start):.1f} seconds")
            print(f"  • Total Blocks / Slips: {self.blocks_count}")
            print(f"  • Total Jabs Thrown:    {self.hits_count}")
            print(f"  • Video Pipeline FPS:   {self.camera_fps:.1f} FPS")
            print("=" * 65)
