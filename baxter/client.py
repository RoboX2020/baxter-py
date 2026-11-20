"""
Baxter Client - High-Level Interface for Rethink Robotics Baxter.
Communicates natively with Baxter via Rosbridge WebSockets (ws://<ip>:9090).
"""

import sys
import time
import math
import json
import socket
import asyncio
import logging
from typing import Dict, List, Optional, Union, Tuple, Any

import websockets

from .poses import JOINTS, POSES, LIMITS
from .limb import Limb
from .head import Head
from .display import Display
from .camera import Camera

logger = logging.getLogger("baxter")


def resolve_baxter_ip(preferred_ip: Optional[str] = None) -> str:
    """Resolves Baxter IP address via hostname or fallback link-local candidates."""
    if preferred_ip:
        try:
            return socket.gethostbyname(preferred_ip)
        except Exception:
            pass
    for host in ["hulk.local", "169.254.127.243", "169.254.9.243", "localhost"]:
        try:
            return socket.gethostbyname(host)
        except Exception:
            continue
    return "169.254.127.243"


class Baxter:
    """
    Primary interface to Rethink Robotics Baxter.
    Provides complete control of limbs, head, display, cameras, and state.
    """

    def __init__(self, host: Optional[str] = None, port: int = 9090):
        self.ip = resolve_baxter_ip(host)
        self.port = port
        self.ws_url = f"ws://{self.ip}:{self.port}"
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False

        # Submodules
        self.left_arm = Limb(self, "left")
        self.right_arm = Limb(self, "right")
        self.head = Head(self)
        self.display = Display(self)
        self.camera = Camera(self)

    @property
    def is_connected(self) -> bool:
        if not self._connected or self.ws is None:
            return False
        if hasattr(self.ws, "closed"):
            return not self.ws.closed
        if hasattr(self.ws, "state"):
            return getattr(self.ws.state, "name", "") == "OPEN"
        return self._connected

    async def connect(self):
        """Connects to the Rosbridge WebSocket server on Baxter."""
        if self.is_connected:
            return
        logger.info(f"Connecting to Baxter at {self.ws_url}...")
        self.ws = await websockets.connect(
            self.ws_url,
            max_size=16 * 1024 * 1024,
            ping_interval=None,
            ping_timeout=None
        )
        self._connected = True

        # Pre-advertise common control topics
        for arm in ("left", "right"):
            await self.advertise(f"/robot/limb/{arm}/suppress_collision_avoidance", "std_msgs/Empty")
            await self.advertise(f"/robot/limb/{arm}/joint_command", "baxter_core_msgs/JointCommand")
        await self.advertise("/robot/head/command_head_pan", "baxter_core_msgs/HeadPanCommand")
        await self.advertise("/robot/head/command_head_nod", "std_msgs/Bool")
        await self.advertise("/robot/set_super_reset", "std_msgs/Empty")
        await self.advertise("/robot/set_super_enable", "std_msgs/Bool")
        await self.advertise("/robot/xdisplay", "sensor_msgs/Image", latch=True)

    async def disconnect(self):
        """Disconnects the WebSocket connection."""
        if self.ws:
            await self.ws.close()
        self._connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    # -------------------------------------------------------------------------
    # Rosbridge Communication Primitives
    # -------------------------------------------------------------------------
    async def send_json(self, payload: dict):
        if not self.is_connected:
            await self.connect()
        await self.ws.send(json.dumps(payload))

    async def advertise(self, topic: str, msg_type: str, latch: bool = False):
        await self.send_json({
            "op": "advertise",
            "topic": topic,
            "type": msg_type,
            "latch": latch
        })

    async def publish(self, topic: str, msg: dict, latch: bool = False):
        await self.send_json({
            "op": "publish",
            "topic": topic,
            "msg": msg,
            "latch": latch
        })

    async def subscribe(self, topic: str):
        await self.send_json({
            "op": "subscribe",
            "topic": topic
        })

    async def unsubscribe(self, topic: str):
        await self.send_json({
            "op": "unsubscribe",
            "topic": topic
        })

    # -------------------------------------------------------------------------
    # Robot State & Safety Interlocks
    # -------------------------------------------------------------------------
    async def get_state(self, timeout: float = 2.0) -> dict:
        """Reads current robot assembly state (/robot/state)."""
        await self.subscribe("/robot/state")
        start = time.time()
        while time.time() - start < timeout:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("topic") == "/robot/state":
                return msg.get("msg", {})
        return {}

    async def get_joint_positions(self, limb: Optional[str] = None, timeout: float = 2.0) -> dict:
        """
        Reads current joint positions from /robot/joint_states.
        If limb ('left' or 'right') is specified, returns only that limb's 7 joints.
        """
        await self.subscribe("/robot/joint_states")
        start = time.time()
        while time.time() - start < timeout:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("topic") == "/robot/joint_states":
                m = msg.get("msg", {})
                d = dict(zip(m.get("name", []), m.get("position", [])))
                if limb:
                    return {j: d.get(j, 0.0) for j in JOINTS[limb]}
                return d
        return {}

    async def get_digital_io(self, timeout: float = 2.0) -> dict:
        """Reads digital IO states (e.g., e-stop inputs)."""
        await self.subscribe("/robot/digital_io_states")
        start = time.time()
        while time.time() - start < timeout:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("topic") == "/robot/digital_io_states":
                m = msg.get("msg", {})
                return dict(zip(m.get("names", []), [s["state"] for s in m.get("states", [])]))
        return {}

    async def enable(self) -> bool:
        """Clears reset state and enables robot motors."""
        # 1. Reset pulse
        await self.publish("/robot/set_super_reset", {})
        await asyncio.sleep(0.3)
        # 2. Enable pulse train
        for _ in range(12):
            await self.publish("/robot/set_super_enable", {"data": True})
            await asyncio.sleep(0.1)
        state = await self.get_state(timeout=2.0)
        return bool(state.get("enabled", False))

    async def disable(self) -> bool:
        """Disables robot motors."""
        for _ in range(5):
            await self.publish("/robot/set_super_enable", {"data": False})
            await asyncio.sleep(0.1)
        state = await self.get_state(timeout=2.0)
        return not bool(state.get("enabled", False))

    async def reset(self) -> bool:
        """Sends reset pulse to clear robot faults."""
        await self.publish("/robot/set_super_reset", {})
        await asyncio.sleep(0.5)
        state = await self.get_state(timeout=2.0)
        return not bool(state.get("error", False))

    # -------------------------------------------------------------------------
    # Coordinated Dual-Arm Motion
    # -------------------------------------------------------------------------
    async def move_to(
        self,
        left: Optional[Union[List[float], Dict[str, float]]] = None,
        right: Optional[Union[List[float], Dict[str, float]]] = None,
        duration: float = 4.0,
        rate: float = 40.0
    ):
        """
        Coordinates smooth simultaneous movement of left and/or right arms.
        Suppresses collision avoidance during motion.
        """
        target_dict = {}
        if left is not None:
            if isinstance(left, dict):
                target_dict["left"] = [left[j] for j in JOINTS["left"]]
            else:
                target_dict["left"] = list(left)
        if right is not None:
            if isinstance(right, dict):
                target_dict["right"] = [right[j] for j in JOINTS["right"]]
            else:
                target_dict["right"] = list(right)

        if not target_dict:
            return

        current_joints = await self.get_joint_positions()
        cmd = {}
        for arm in target_dict:
            cmd[arm] = [current_joints.get(j, 0.0) for j in JOINTS[arm]]

        start_time = time.time()
        dt = 1.0 / rate
        alpha = 0.045 # First-order low pass filter coefficient

        while time.time() - start_time < duration:
            for arm, targets in target_dict.items():
                await self.publish(f"/robot/limb/{arm}/suppress_collision_avoidance", {})
                for i in range(7):
                    cmd[arm][i] = alpha * targets[i] + (1.0 - alpha) * cmd[arm][i]

                await self.publish(f"/robot/limb/{arm}/joint_command", {
                    "mode": 1, # POSITION_MODE
                    "names": JOINTS[arm],
                    "command": cmd[arm]
                })
            await asyncio.sleep(dt)

        # Hold final pose briefly
        for _ in range(12):
            for arm, targets in target_dict.items():
                await self.publish(f"/robot/limb/{arm}/suppress_collision_avoidance", {})
                await self.publish(f"/robot/limb/{arm}/joint_command", {
                    "mode": 1,
                    "names": JOINTS[arm],
                    "command": targets
                })
            await asyncio.sleep(dt)

    # -------------------------------------------------------------------------
    # Convenience Poses
    # -------------------------------------------------------------------------
    async def untuck(self, duration: float = 4.5):
        """Moves both arms from tuck to symmetrical neutral operational posture."""
        await self.move_to(left=POSES["neutral"]["left"], right=POSES["neutral"]["right"], duration=duration)
        await self.head.pan(0.0)

    async def tuck(self, duration: float = 5.0):
        """Safely folds both arms into compact shipping/storage configuration."""
        await self.move_to(left=POSES["tuck"]["left"], right=POSES["tuck"]["right"], duration=duration)

    async def wave(self, arm: str = "right", cycles: int = 3):
        """Waves friendly greeting with specified arm (default right)."""
        if arm == "right":
            await self.move_to(right=POSES["wave"]["ready"]["right"], duration=2.5)
            await self.head.pan(-0.35)
            for _ in range(cycles):
                await self.move_to(right=POSES["wave"]["wave_left"]["right"], duration=0.55)
                await self.move_to(right=POSES["wave"]["wave_right"]["right"], duration=0.55)
            await self.head.pan(0.0)
            await self.move_to(right=POSES["neutral"]["right"], duration=2.5)
            await self.head.nod()

    async def cheer(self, duration: float = 3.5):
        """Raises both arms in celebratory victory cheer."""
        await self.move_to(left=POSES["cheer"]["left"], right=POSES["cheer"]["right"], duration=duration)
        await self.head.nod()
        await asyncio.sleep(1.5)
        await self.untuck(duration=duration)

    async def salute(self, duration: float = 3.0):
        """Executes a crisp right arm salute."""
        await self.move_to(right=POSES["salute"]["right"], duration=duration)
        await self.head.nod()
        await asyncio.sleep(1.5)
        await self.untuck(duration=duration)
