"""
Baxter Camera Controller - Video Acquisition and Frame Decoding.
Connects to Baxter's onboard cameras (head_camera, left_hand_camera, right_hand_camera).
"""

import base64
import asyncio
from typing import Optional, Tuple, AsyncIterator, Union
import numpy as np
import cv2


class Camera:
    """Acquires image frames from Baxter's onboard cameras."""

    def __init__(self, baxter: "Baxter"):
        self.baxter = baxter
        self.default_camera = "head_camera"

    async def open(self, camera_name: str = "head_camera", width: int = 640, height: int = 400, fps: int = 20):
        """Requests camera activation via /cameras/open service."""
        # Typically Baxter provides /cameras/open service or automatic topic publishing
        # Subscribing to the image topic starts the Rosbridge stream
        topic = f"/cameras/{camera_name}/image"
        await self.baxter.subscribe(topic)

    async def close(self, camera_name: str = "head_camera"):
        """Unsubscribes from camera image topic."""
        topic = f"/cameras/{camera_name}/image"
        await self.baxter.unsubscribe(topic)

    async def read(self, camera_name: str = "head_camera", timeout: float = 3.0) -> Optional[np.ndarray]:
        """
        Reads a single BGR image frame from the specified camera.
        Returns numpy.ndarray with shape (height, width, 3) or None on timeout.
        """
        topic = f"/cameras/{camera_name}/image"
        await self.baxter.subscribe(topic)

        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            raw = await asyncio.wait_for(self.baxter.ws.recv(), timeout=timeout)
            import json
            msg = json.loads(raw)
            if msg.get("topic") == topic:
                m = msg.get("msg", {})
                h = m.get("height", 0)
                w = m.get("width", 0)
                encoding = m.get("encoding", "")
                data_b64 = m.get("data", "")
                if not data_b64 or h == 0 or w == 0:
                    continue

                raw_bytes = base64.b64decode(data_b64)
                if len(raw_bytes) == h * w * 4 or "8" in encoding:
                    frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((h, w, 4))[:, :, :3]
                elif len(raw_bytes) == h * w * 3:
                    frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((h, w, 3))
                else:
                    continue

                if camera_name == "head_camera":
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                return frame

        return None

    async def stream(self, camera_name: Union[str, int] = "head_camera") -> AsyncIterator[np.ndarray]:
        """
        Async generator that yields decoded BGR frames as they arrive.
        Supports both Baxter onboard cameras ('head_camera', 'left_hand_camera', etc.)
        and local external USB cameras (e.g. 0, '0', or '/dev/video0').
        """
        # 1. Local USB / External Camera
        is_usb = isinstance(camera_name, int) or (isinstance(camera_name, str) and (camera_name.isdigit() or "/dev/video" in camera_name))
        if is_usb:
            dev_idx = int(camera_name) if str(camera_name).isdigit() else camera_name
            cap = cv2.VideoCapture(dev_idx)
            if not cap.isOpened():
                raise RuntimeError(f"Could not open external camera {camera_name}")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            try:
                loop = asyncio.get_event_loop()
                while self.baxter.is_connected or True:
                    ret, frame = await loop.run_in_executor(None, cap.read)
                    if not ret:
                        await asyncio.sleep(0.01)
                        continue
                    yield frame
                    await asyncio.sleep(0.001)
            finally:
                cap.release()
            return

        # 2. Baxter Onboard Network Camera via Rosbridge WebSocket
        topic = f"/cameras/{camera_name}/image"
        await self.baxter.subscribe(topic)
        import json

        while self.baxter.is_connected:
            raw = await self.baxter.ws.recv()
            msg = json.loads(raw)
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

                    if camera_name == "head_camera":
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    yield frame
