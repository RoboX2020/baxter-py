"""
Baxter Display Controller - Head Screen X11 Graphics & Vector Face Emotions.
Renders to Baxter's 1024x600 LCD screen via /robot/xdisplay.
"""

import io
import math
import time
import base64
import asyncio
from typing import Optional, Union, Tuple
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1024
HEIGHT = 600

# Built-in font lookup
FONT_PATH_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_PATH_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

try:
    FONT_LARGE = ImageFont.truetype(FONT_PATH_BOLD, 26)
    FONT_MEDIUM = ImageFont.truetype(FONT_PATH_BOLD, 20)
    FONT_SMALL = ImageFont.truetype(FONT_PATH_REG, 16)
except Exception:
    FONT_LARGE = ImageFont.load_default()
    FONT_MEDIUM = ImageFont.load_default()
    FONT_SMALL = ImageFont.load_default()


class Display:
    """Controls Baxter's 1024x600 head screen."""

    def __init__(self, baxter: "Baxter"):
        self.baxter = baxter
        self._seq = 1

    async def publish_image(self, img: Image.Image):
        """Encodes PIL Image to BGR raw bytes and publishes to /robot/xdisplay."""
        if img.size != (WIDTH, HEIGHT):
            img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

        if img.mode != "RGB":
            img = img.convert("RGB")

        # Convert RGB PIL to BGR raw bytes
        r, g, b = img.split()
        bgr = Image.merge("RGB", (b, g, r))
        raw_bgr = bgr.tobytes()
        b64_data = base64.b64encode(raw_bgr).decode("ascii")

        msg = {
            "header": {"seq": self._seq, "stamp": {"secs": 0, "nsecs": 0}, "frame_id": "head"},
            "height": HEIGHT,
            "width": WIDTH,
            "encoding": "bgr8",
            "is_bigendian": 0,
            "step": WIDTH * 3,
            "data": b64_data
        }
        self._seq += 1
        await self.baxter.publish("/robot/xdisplay", msg, latch=True)

    async def show_file(self, image_path: str):
        """Loads an image from disk and displays it."""
        img = Image.open(image_path)
        await self.publish_image(img)

    async def show_emotion(
        self,
        emotion: str = "neutral",
        status_text: Optional[str] = None,
        eye_offset_x: int = 0,
        eye_offset_y: int = 0
    ):
        """
        Renders and displays a stylized vector robot face.
        Emotions: neutral, happy, focused, wink, boxing, disco, surprised, sleepy.
        """
        img = self.render_face(
            emotion=emotion,
            status_text=status_text or f"BAXTER | EMOTION: {emotion.upper()}",
            eye_offset_x=eye_offset_x,
            eye_offset_y=eye_offset_y
        )
        await self.publish_image(img)

    @staticmethod
    def render_face(
        emotion: str = "neutral",
        status_text: str = "BAXTER ONLINE",
        eye_offset_x: int = 0,
        eye_offset_y: int = 0
    ) -> Image.Image:
        """Generates PIL Image of Baxter's face with specific expression."""
        img = Image.new("RGB", (WIDTH, HEIGHT), color=(12, 28, 48))
        draw = ImageDraw.Draw(img)

        # Header bar
        draw.rectangle([0, 0, WIDTH, 48], fill=(6, 16, 28))
        draw.text((30, 12), "RETHINK ROBOTICS BAXTER", fill=(0, 210, 255), font=FONT_LARGE)
        draw.text((WIDTH - 280, 15), "INTERFACE: BAXTER-PY", fill=(140, 170, 200), font=FONT_SMALL)

        left_center = (340, 280)
        right_center = (684, 280)

        # Draw eyes based on emotion
        if emotion in ("sleepy", "closed"):
            draw.arc([left_center[0] - 80, left_center[1] - 40, left_center[0] + 80, left_center[1] + 40],
                     start=20, end=160, fill=(0, 220, 255), width=16)
            draw.arc([right_center[0] - 80, right_center[1] - 40, right_center[0] + 80, right_center[1] + 40],
                     start=20, end=160, fill=(0, 220, 255), width=16)
        elif emotion == "wink":
            # Left eye open, right eye winking
            draw.ellipse([left_center[0] - 90, left_center[1] - 120, left_center[0] + 90, left_center[1] + 120], fill=(0, 180, 230))
            draw.ellipse([left_center[0] - 78, left_center[1] - 108, left_center[0] + 78, left_center[1] + 108], fill=(230, 250, 255))
            draw.ellipse([left_center[0] - 40 + eye_offset_x, left_center[1] - 50 + eye_offset_y,
                          left_center[0] + 40 + eye_offset_x, left_center[1] + 50 + eye_offset_y], fill=(15, 40, 75))
            draw.arc([right_center[0] - 80, right_center[1] - 40, right_center[0] + 80, right_center[1] + 40],
                     start=200, end=340, fill=(0, 220, 255), width=16)
        elif emotion == "disco":
            # Shutter shades / retro futuristic neon visor
            draw.rounded_rectangle([left_center[0] - 120, left_center[1] - 80, right_center[0] + 120, left_center[1] + 80],
                                   radius=20, fill=(20, 10, 40), outline=(255, 0, 128), width=8)
            for y in range(left_center[1] - 60, left_center[1] + 70, 22):
                draw.line([(left_center[0] - 110, y), (right_center[0] + 110, y)], fill=(0, 255, 240), width=6)
        elif emotion == "boxing":
            # Intense fighter eyes & headgear outline
            draw.ellipse([WIDTH // 2 - 150, 140, WIDTH // 2 + 150, 360], fill=(220, 25, 45))
            draw.ellipse([WIDTH // 2 - 110, 175, WIDTH // 2 + 110, 325], fill=(16, 30, 56))
            # Slanted eyes
            draw.polygon([(left_center[0] - 60, left_center[1] - 30), (left_center[0] + 60, left_center[1] - 10),
                          (left_center[0] + 50, left_center[1] + 20), (left_center[0] - 50, left_center[1] + 10)],
                         fill=(255, 220, 0))
            draw.polygon([(right_center[0] - 60, right_center[1] - 10), (right_center[0] + 60, right_center[1] - 30),
                          (right_center[0] + 50, right_center[1] + 10), (right_center[0] - 50, right_center[1] + 20)],
                         fill=(255, 220, 0))
        else: # Normal / Happy / Surprised
            # Eye outer ring
            draw.ellipse([left_center[0] - 92, left_center[1] - 122, left_center[0] + 92, left_center[1] + 122], fill=(0, 180, 230))
            draw.ellipse([right_center[0] - 92, right_center[1] - 122, right_center[0] + 92, right_center[1] + 122], fill=(0, 180, 230))
            # Eye sclera
            draw.ellipse([left_center[0] - 80, left_center[1] - 110, left_center[0] + 80, left_center[1] + 110], fill=(230, 250, 255))
            draw.ellipse([right_center[0] - 80, right_center[1] - 110, right_center[0] + 80, right_center[1] + 110], fill=(230, 250, 255))
            # Pupils
            px_l = left_center[0] + eye_offset_x
            py_l = left_center[1] + eye_offset_y
            px_r = right_center[0] + eye_offset_x
            py_r = right_center[1] + eye_offset_y
            draw.ellipse([px_l - 40, py_l - 52, px_l + 40, py_l + 52], fill=(15, 40, 75))
            draw.ellipse([px_r - 40, py_r - 52, px_r + 40, py_r + 52], fill=(15, 40, 75))
            # Iris highlight
            draw.ellipse([px_l + 8, py_l - 32, px_l + 30, py_l - 10], fill=(255, 255, 255))
            draw.ellipse([px_r + 8, py_r - 32, px_r + 30, py_r - 10], fill=(255, 255, 255))

            # Eyebrows
            brow_tilt = -12 if emotion == "happy" else (12 if emotion == "focused" else 0)
            draw.rounded_rectangle([left_center[0] - 80, 130 + brow_tilt, left_center[0] + 80, 152 + brow_tilt], radius=10, fill=(0, 220, 255))
            draw.rounded_rectangle([right_center[0] - 80, 130 - brow_tilt, right_center[0] + 80, 152 - brow_tilt], radius=10, fill=(0, 220, 255))

        # Mouth
        if emotion in ("happy", "neutral", "wink", "disco"):
            draw.arc([440, 400, 584, 480], start=20, end=160, fill=(0, 220, 255), width=9)
        elif emotion == "surprised":
            draw.ellipse([480, 410, 544, 474], fill=(0, 180, 230), outline=(0, 220, 255), width=6)

        # Footer status
        draw.rectangle([0, HEIGHT - 52, WIDTH, HEIGHT], fill=(6, 16, 28))
        draw.text((30, HEIGHT - 38), status_text, fill=(0, 255, 180), font=FONT_LARGE)
        draw.text((WIDTH - 250, HEIGHT - 34), "BAXTER-PY DISPLAY", fill=(140, 170, 200), font=FONT_SMALL)

        return img
