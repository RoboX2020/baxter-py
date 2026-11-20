"""
Baxter Vision & AI - MediaPipe Hand Tracking and Interactive Boxing Sparring.
"""

import os
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
from .display import Display, WIDTH, HEIGHT

# Model path
DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
DEFAULT_MODEL_PATH = os.path.join(DEFAULT_MODEL_DIR, "gesture_recognizer.task")


class GestureDetector:
    """Wrapper around MediaPipe Gesture Recognizer."""

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
            min_hand_detection_confidence=0.55,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55
        )
        self.recognizer = mp_vision.GestureRecognizer.create_from_options(options)

    def detect(self, bgr_frame: np.ndarray) -> List[Dict]:
        """
        Runs gesture recognition on BGR image.
        Returns list of detected hands with 'gesture', 'score', and 'wrist' (x, y).
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
                if result.hand_landmarks and i < len(result.hand_landmarks):
                    landmarks = result.hand_landmarks[i]
                    wrist = (landmarks[0].x, landmarks[0].y)

                detections.append({
                    "gesture": top.category_name,
                    "score": top.score,
                    "wrist": wrist
                })
        return detections


class BoxerSparring:
    """Interactive Boxing AI Partner powered by real-time vision."""

    def __init__(self, baxter: "Baxter", model_path: Optional[str] = None):
        self.baxter = baxter
        self.detector = GestureDetector(model_path)

    async def run(self, duration_sec: float = 60.0):
        """Runs the interactive sparring session."""
        print("=" * 65)
        print("🥊 STARTING BAXTER BOXING SPARRING SESSION 🥊")
        print("=" * 65)
        print("  • Punch (Closed Fist)  --> High Block & Slip")
        print("  • Pad (Open Palm)      --> Target Jab")
        print("  • Thumbs Up            --> Champion Celebration")
        print("  • Hand Motion          --> Dynamic Head & Gaze Tracking")

        boxing_poses = POSES["boxing"]
        await self.baxter.move_to(left=boxing_poses["guard"]["left"], right=boxing_poses["guard"]["right"], duration=3.0)
        await self.baxter.head.pan(0.0)

        t_start = time.time()
        hits_count = 0
        blocks_count = 0
        active_mode = "guard"
        action_until = 0.0
        last_action_time = 0.0

        async for frame in self.baxter.camera.stream("head_camera"):
            now = time.time()
            if now - t_start > duration_sec:
                break

            detections = self.detector.detect(frame)
            gesture = None
            hand_x, hand_y = 0.5, 0.5

            if detections:
                top = detections[0]
                gesture = top["gesture"]
                confidence = top["score"]
                hand_x, hand_y = top["wrist"]

                # Head tracking: Baxter mirrors opponent's position
                target_pan = float(np.clip((0.5 - hand_x) * 1.5, -0.65, 0.65))
                await self.baxter.head.pan(target_pan, speed_ratio=0.7)

                # State machine triggers
                if now > action_until and now - last_action_time > 0.8:
                    if gesture == "Closed_Fist" and confidence > 0.55:
                        # Opponent punches: block with the side closest to punch
                        blocks_count += 1
                        last_action_time = now
                        action_until = now + 1.2
                        if hand_x < 0.5:
                            active_mode = "block_right"
                            await self.baxter.move_to(right=boxing_poses["block_right"]["right"], duration=0.35)
                        else:
                            active_mode = "block_left"
                            await self.baxter.move_to(left=boxing_poses["block_left"]["left"], duration=0.35)

                    elif gesture == "Open_Palm" and confidence > 0.55:
                        # Opponent holds target pad: throw straight jab
                        hits_count += 1
                        last_action_time = now
                        action_until = now + 1.2
                        if hand_x < 0.5:
                            active_mode = "jab_right"
                            await self.baxter.move_to(right=boxing_poses["jab_right"]["right"], duration=0.35)
                        else:
                            active_mode = "jab_left"
                            await self.baxter.move_to(left=boxing_poses["jab_left"]["left"], duration=0.35)

                    elif gesture in ("Thumb_Up", "Victory"):
                        last_action_time = now
                        action_until = now + 2.0
                        active_mode = "celebrate"
                        await self.baxter.move_to(left=POSES["cheer"]["left"], right=POSES["cheer"]["right"], duration=1.2)
                        await self.baxter.head.nod()

            # Return to guard if action finished
            if now > action_until and active_mode != "guard":
                active_mode = "guard"
                await self.baxter.move_to(left=boxing_poses["guard"]["left"], right=boxing_poses["guard"]["right"], duration=0.6)

            # Update display face
            await self.baxter.display.show_emotion(
                emotion="boxing",
                status_text=f"ROUND: {int(duration_sec - (now - t_start))}s | BLOCKS: {blocks_count} | JABS: {hits_count}",
                eye_offset_x=int((hand_x - 0.5) * 60),
                eye_offset_y=int((hand_y - 0.5) * 40)
            )

        # Return to neutral at end
        print("\n[✓] Sparring round finished! Returning to neutral pose...")
        await self.baxter.untuck()
        await self.baxter.display.show_emotion("happy", status_text="GREAT SPARRING MATCH!")
