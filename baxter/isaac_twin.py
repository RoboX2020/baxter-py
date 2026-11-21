"""
NVIDIA Isaac Sim - Baxter 3D Digital Twin & Bidirectional Sim-to-Real / Real-to-Sim Bridge.
Includes Interactive Keyboard Teleoperation & Real-Time Motor Synchronization.
"""

import os
import sys
import time
import json
import socket
import select
import termios
import tty
import asyncio
import argparse
import threading
from typing import Dict, List, Optional, Tuple

import torch
from isaaclab.app import add_launcher_args, launch_simulation
import isaaclab.sim as sim_utils

# Argument parsing
parser = argparse.ArgumentParser(description="Baxter Digital Twin - Isaac Sim Bridge & Teleoperation")
parser.add_argument("--host", default="169.254.127.243", help="Physical Baxter IP address")
parser.add_argument("--port", type=int, default=9090, help="Rosbridge WebSocket port")
parser.add_argument("--udp-port", type=int, default=19888, help="Local UDP parallel command port")
parser.add_argument("--sim-to-real", action="store_true", help="Enable commanding physical robot from simulation")
parser.add_argument("--headless", action="store_true", help="Run without opening 3D GUI window")
add_launcher_args(parser)
args_cli = parser.parse_args()

# Enable 3D Kit visualizer window when not headless
if not args_cli.headless and not args_cli.visualizer:
    args_cli.visualizer = ["kit"]


# Joint definitions and physical safety limits (radians)
JOINTS = {
    'left': ['left_s0', 'left_s1', 'left_e0', 'left_e1', 'left_w0', 'left_w1', 'left_w2'],
    'right': ['right_s0', 'right_s1', 'right_e0', 'right_e1', 'right_w0', 'right_w1', 'right_w2']
}

LIMITS = {
    's0': (-1.701, 1.701),
    's1': (-2.147, 1.047),
    'e0': (-3.054, 3.054),
    'e1': (-0.050, 2.618),
    'w0': (-3.059, 3.059),
    'w1': (-1.571, 2.094),
    'w2': (-3.059, 3.059),
    'head_pan': (-1.57, 1.57)
}

POSES = {
    'neutral': {
        'left':  [-0.08, -1.00, -1.19, 1.94,  0.67, 1.03, -0.50],
        'right': [ 0.08, -1.00,  1.19, 1.94, -0.67, 1.03,  0.50]
    },
    'tuck': {
        'left':  [-1.00, -2.07,  3.00, 2.55,  0.00, 0.01,  0.00],
        'right': [ 1.00, -2.07, -3.00, 2.55, -0.00, 0.01,  0.00]
    },
    'wave': {
        'left':  [-0.08, -1.00, -1.19, 1.94,  0.67, 1.03, -0.50],
        'right': [ 0.25, -0.65,  0.30, 2.15,  0.00, -0.35, 0.00]
    },
    'boxing': {
        'left':  [-0.15, -0.65, -0.50, 2.05,  0.40,  0.40, -0.20],
        'right': [ 0.15, -0.65,  0.50, 2.05, -0.40,  0.40,  0.20]
    },
    'cheer': {
        'left':  [-0.55, -0.60, -0.45, 0.65,  0.00, 0.00, 0.00],
        'right': [ 0.55, -0.60,  0.45, 0.65,  0.00, 0.00, 0.00]
    },
    'reach': {
        'left':  [-0.15, -0.30, -0.20, 0.85,  0.00, 0.20, 0.00],
        'right': [ 0.15, -0.30,  0.20, 0.85,  0.00, 0.20, 0.00]
    },
    'salute': {
        'left':  [-0.08, -1.00, -1.19, 1.94,  0.67, 1.03, -0.50],
        'right': [ 0.10, -0.80,  1.20, 2.20,  0.50, 0.30, 0.00]
    }
}


# Shared thread-safe state
state_lock = threading.Lock()
real_joint_positions: Dict[str, float] = {}
sim_target_positions: Dict[str, float] = {}
is_real_connected = False
sim_to_real_enabled = args_cli.sim_to_real
active_arm = "right"
active_joint_idx = 1 # Start on s1 (shoulder pitch)
running = True
last_user_action = "Initialized in Neutral Pose"


# Initialize sim targets to neutral pose
for arm in ["left", "right"]:
    for name, val in zip(JOINTS[arm], POSES["neutral"][arm]):
        sim_target_positions[name] = float(val)
sim_target_positions["head_pan"] = 0.0


def clamp_joint(joint_name: str, val: float) -> float:
    """Clamps joint angle within Baxter hardware physical safety limits."""
    for key, (lo, hi) in LIMITS.items():
        if joint_name.endswith(key) or joint_name == key:
            return max(lo, min(hi, val))
    return val


def handle_key_action(key: str):
    """Processes keyboard input commands for poses, joint jogs, and mode switches."""
    global active_arm, active_joint_idx, sim_to_real_enabled, last_user_action, running

    with state_lock:
        joint_list = JOINTS[active_arm]
        curr_joint = joint_list[active_joint_idx]
        short_name = curr_joint.replace(f"{active_arm}_", "")

        # 1. Preset Poses
        if key == '1':
            for arm in ["left", "right"]:
                for n, v in zip(JOINTS[arm], POSES["neutral"][arm]):
                    sim_target_positions[n] = float(v)
            last_user_action = "Pose -> NEUTRAL (Ready Stance)"
        elif key == '2':
            for arm in ["left", "right"]:
                for n, v in zip(JOINTS[arm], POSES["wave"][arm]):
                    sim_target_positions[n] = float(v)
            sim_target_positions["head_pan"] = 0.25
            last_user_action = "Pose -> WAVE (Right Arm Elevated)"
        elif key == '3':
            for arm in ["left", "right"]:
                for n, v in zip(JOINTS[arm], POSES["boxing"][arm]):
                    sim_target_positions[n] = float(v)
            sim_target_positions["head_pan"] = 0.0
            last_user_action = "Pose -> BOXING GUARD"
        elif key == '4':
            for arm in ["left", "right"]:
                for n, v in zip(JOINTS[arm], POSES["cheer"][arm]):
                    sim_target_positions[n] = float(v)
            last_user_action = "Pose -> CHEER (High Victory)"
        elif key == '5':
            for arm in ["left", "right"]:
                for n, v in zip(JOINTS[arm], POSES["reach"][arm]):
                    sim_target_positions[n] = float(v)
            last_user_action = "Pose -> REACH FORWARD"
        elif key == '0':
            for arm in ["left", "right"]:
                for n, v in zip(JOINTS[arm], POSES["tuck"][arm]):
                    sim_target_positions[n] = float(v)
            last_user_action = "Pose -> TUCK (Compact Storage)"

        # 2. Arm Toggle
        elif key in ('\t', ' '):
            active_arm = "left" if active_arm == "right" else "right"
            last_user_action = f"Selected Arm -> {active_arm.upper()}"

        # 3. Joint Selection (q, w, e, r, t, y, u)
        elif key == 'q':
            active_joint_idx = 0 # s0
            last_user_action = f"Selected Joint -> {active_arm}_s0 (Shoulder Pan)"
        elif key == 'w':
            active_joint_idx = 1 # s1
            last_user_action = f"Selected Joint -> {active_arm}_s1 (Shoulder Pitch)"
        elif key == 'e':
            active_joint_idx = 2 # e0
            last_user_action = f"Selected Joint -> {active_arm}_e0 (Elbow Roll)"
        elif key == 'r':
            active_joint_idx = 3 # e1
            last_user_action = f"Selected Joint -> {active_arm}_e1 (Elbow Pitch)"
        elif key == 't':
            active_joint_idx = 4 # w0
            last_user_action = f"Selected Joint -> {active_arm}_w0 (Wrist Roll)"
        elif key == 'y':
            active_joint_idx = 5 # w1
            last_user_action = f"Selected Joint -> {active_arm}_w1 (Wrist Pitch)"
        elif key == 'u':
            active_joint_idx = 6 # w2
            last_user_action = f"Selected Joint -> {active_arm}_w2 (Wrist Roll)"

        # 4. Jog Selected Joint (+/- 0.08 rad / ~4.6 deg)
        elif key in ('+', '=', 'k', 'A'): # A is Up arrow escape
            delta = 0.08
            new_val = clamp_joint(curr_joint, sim_target_positions.get(curr_joint, 0.0) + delta)
            sim_target_positions[curr_joint] = new_val
            last_user_action = f"Jog + {curr_joint}: {new_val:+.3f} rad ({new_val*57.2958:+.1f}°)"
        elif key in ('-', '_', 'j', 'B'): # B is Down arrow escape
            delta = -0.08
            new_val = clamp_joint(curr_joint, sim_target_positions.get(curr_joint, 0.0) + delta)
            sim_target_positions[curr_joint] = new_val
            last_user_action = f"Jog - {curr_joint}: {new_val:+.3f} rad ({new_val*57.2958:+.1f}°)"

        # 5. Direct Arm Directional Jogging (WASD / RF / TG)
        elif key == 'W':
            # Shoulder pitch UP
            j = f"{active_arm}_s1"
            new_val = clamp_joint(j, sim_target_positions.get(j, 0.0) + 0.08)
            sim_target_positions[j] = new_val
            last_user_action = f"Arm UP ({j}): {new_val*57.2958:+.1f}°"
        elif key in ('S', 's'):
            # Shoulder pitch DOWN
            j = f"{active_arm}_s1"
            new_val = clamp_joint(j, sim_target_positions.get(j, 0.0) - 0.08)
            sim_target_positions[j] = new_val
            last_user_action = f"Arm DOWN ({j}): {new_val*57.2958:+.1f}°"
        elif key in ('A', 'a'):
            # Shoulder pan OUTWARD / LEFT
            j = f"{active_arm}_s0"
            delta = -0.08 if active_arm == "right" else 0.08
            new_val = clamp_joint(j, sim_target_positions.get(j, 0.0) + delta)
            sim_target_positions[j] = new_val
            last_user_action = f"Arm OUTWARD ({j}): {new_val*57.2958:+.1f}°"
        elif key in ('D', 'd'):
            # Shoulder pan INWARD / RIGHT
            j = f"{active_arm}_s0"
            delta = 0.08 if active_arm == "right" else -0.08
            new_val = clamp_joint(j, sim_target_positions.get(j, 0.0) + delta)
            sim_target_positions[j] = new_val
            last_user_action = f"Arm INWARD ({j}): {new_val*57.2958:+.1f}°"
        elif key == 'R':
            # Elbow pitch FLEX
            j = f"{active_arm}_e1"
            new_val = clamp_joint(j, sim_target_positions.get(j, 0.0) + 0.08)
            sim_target_positions[j] = new_val
            last_user_action = f"Elbow FLEX ({j}): {new_val*57.2958:+.1f}°"
        elif key in ('F', 'f'):
            # Elbow pitch EXTEND
            j = f"{active_arm}_e1"
            new_val = clamp_joint(j, sim_target_positions.get(j, 0.0) - 0.08)
            sim_target_positions[j] = new_val
            last_user_action = f"Elbow EXTEND ({j}): {new_val*57.2958:+.1f}°"
        elif key in ('G', 'g'):
            # Wrist pitch EXTEND
            j = f"{active_arm}_w1"
            new_val = clamp_joint(j, sim_target_positions.get(j, 0.0) - 0.08)
            sim_target_positions[j] = new_val
            last_user_action = f"Wrist pitch EXTEND ({j}): {new_val*57.2958:+.1f}°"

        # 6. Head Pan Controls
        elif key == '[':
            new_val = clamp_joint('head_pan', sim_target_positions.get('head_pan', 0.0) + 0.10)
            sim_target_positions['head_pan'] = new_val
            last_user_action = f"Head PAN LEFT: {new_val*57.2958:+.1f}°"
        elif key == ']':
            new_val = clamp_joint('head_pan', sim_target_positions.get('head_pan', 0.0) - 0.10)
            sim_target_positions['head_pan'] = new_val
            last_user_action = f"Head PAN RIGHT: {new_val*57.2958:+.1f}°"
        elif key == 'c':
            sim_target_positions['head_pan'] = 0.0
            last_user_action = "Head PAN CENTER (0.0°)"

        # 7. Sim-to-Real Mode Toggle
        elif key == 'm':
            sim_to_real_enabled = not sim_to_real_enabled
            status_str = "ACTIVE (Real Baxter Mirroring Sim)" if sim_to_real_enabled else "PAUSED (Sim Only)"
            last_user_action = f"Sim-to-Real Sync -> {status_str}"

        # 8. Help Overlay
        elif key == 'h':
            print_help_banner()

        # 9. Exit
        elif key in ('\x1b', 'x', '\x03'):
            running = False


def print_help_banner():
    """Prints the comprehensive teleoperation keyboard mapping cheat sheet."""
    print("\n" + "=" * 76)
    print("        🎮 BAXTER ISAAC SIM TELEOPERATION - KEYBOARD CONTROLS 🎮")
    print("=" * 76)
    print("  [1] Neutral / Ready Pose      [2] Wave Gesture       [3] Boxing Guard")
    print("  [4] Cheer / Victory           [5] Reach Forward      [0] Tuck Arms")
    print("  ----------------------------------------------------------------------")
    print("  [Tab] or [Space] : Toggle Active Arm (RIGHT <-> LEFT)")
    print("  Joint Selection  : [q]=s0, [w]=s1, [e]=e0, [r]=e1, [t]=w0, [y]=w1, [u]=w2")
    print("  Jog Joint        : [+] or [k] = +5°   |   [-] or [j] = -5°")
    print("  Direct Moves     : [W]/[S]=Shoulder Pitch | [A]/[D]=Shoulder Pan")
    print("                     [R]/[F]=Elbow Pitch    | [T]/[G]=Wrist Pitch")
    print("  Head Pan         : [[] = Pan Left         | []] = Pan Right   | [c] = Center")
    print("  Sim-to-Real      : [m] Toggle Real Baxter Synchronization (ON / OFF)")
    print("  [h] Help Overlay | [Esc] / [x] Exit Safely")
    print("=" * 76 + "\n")


def terminal_keyboard_thread():
    """Background thread: Captures raw keyboard strokes from terminal or pipe."""
    global running
    is_tty = sys.stdin.isatty()
    if is_tty:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while running:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch = sys.stdin.read(1)
                    if not ch:
                        break
                    # Handle arrow keys (ANSI escape sequence \x1b[A, \x1b[B, etc.)
                    if ch == '\x1b':
                        r2, _, _ = select.select([sys.stdin], [], [], 0.02)
                        if r2:
                            ch2 = sys.stdin.read(1)
                            if ch2 == '[':
                                ch3 = sys.stdin.read(1)
                                handle_key_action(ch3) # 'A' is UP, 'B' is DOWN
                                continue
                    handle_key_action(ch)
        except Exception:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    else:
        try:
            while running:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch = sys.stdin.read(1)
                    if not ch:
                        break
                    if ch not in ('\r', '\n'):
                        handle_key_action(ch)
        except Exception:
            pass


def rosbridge_real_to_sim_thread(host: str, port: int):
    """
    Background thread: Streams real Baxter joint encoder states via Rosbridge.
    Updates simulation when sim-to-real is inactive.
    """
    global is_real_connected, real_joint_positions, running
    import websockets

    async def _runner():
        global is_real_connected
        uri = f"ws://{host}:{port}"
        print(f"[*] Real-to-Sim Bridge: Connecting to physical Baxter at {uri}...")

        while running:
            try:
                async with websockets.connect(uri, max_size=32 * 1024 * 1024, ping_interval=5, ping_timeout=10) as ws:
                    await ws.send(json.dumps({
                        "op": "subscribe",
                        "topic": "/robot/joint_states"
                    }))
                    is_real_connected = True
                    print(f"[✓] Real-to-Sim: Connected to physical Baxter! Streaming real joint states.")

                    initial_sync_done = False
                    while running:
                        raw = await ws.recv()
                        data = json.loads(raw)
                        if data.get("topic") == "/robot/joint_states":
                            msg = data.get("msg", {})
                            names = msg.get("name", [])
                            positions = msg.get("position", [])
                            with state_lock:
                                for name, pos in zip(names, positions):
                                    real_joint_positions[name] = pos

                                # On startup, seed simulation targets with physical Baxter's actual stance
                                if not initial_sync_done and "Initialized" in last_user_action:
                                    for j in JOINTS["left"] + JOINTS["right"]:
                                        if j in real_joint_positions:
                                            sim_target_positions[j] = real_joint_positions[j]
                                    if "head_pan" in real_joint_positions:
                                        sim_target_positions["head_pan"] = real_joint_positions["head_pan"]
                                    initial_sync_done = True
            except Exception:
                is_real_connected = False
                await asyncio.sleep(2.0)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_runner())
    except Exception:
        pass


def rosbridge_sim_to_real_thread(host: str, port: int):
    """
    Background thread: High-frequency command stream commanding physical Baxter
    from Isaac Sim simulation joint states in lockstep.
    """
    global is_real_connected, running, sim_to_real_enabled
    import websockets

    async def _sender():
        uri = f"ws://{host}:{port}"

        while running:
            if not sim_to_real_enabled:
                await asyncio.sleep(0.1)
                continue
            try:
                async with websockets.connect(uri, max_size=16 * 1024 * 1024) as ws:
                    # 1. Advertise joint command & collision suppression topics
                    for arm in ["left", "right"]:
                        await ws.send(json.dumps({
                            "op": "advertise",
                            "topic": f"/robot/limb/{arm}/joint_command",
                            "type": "baxter_core_msgs/JointCommand"
                        }))
                        await ws.send(json.dumps({
                            "op": "advertise",
                            "topic": f"/robot/limb/{arm}/suppress_collision_avoidance",
                            "type": "std_msgs/Empty"
                        }))
                    await ws.send(json.dumps({
                        "op": "advertise",
                        "topic": "/robot/head/command_head_pan",
                        "type": "baxter_core_msgs/HeadPanCommand"
                    }))

                    print(f"[✓] Sim-to-Real: Parallel command stream ACTIVE -> Real Baxter is mirroring Isaac Sim!")

                    alpha = 0.15 # Low-pass filter for smooth motion
                    filtered = {"left": None, "right": None}

                    while running and sim_to_real_enabled:
                        with state_lock:
                            left_targets = [sim_target_positions.get(j, 0.0) for j in JOINTS["left"]]
                            right_targets = [sim_target_positions.get(j, 0.0) for j in JOINTS["right"]]
                            head_target = sim_target_positions.get("head_pan", 0.0)

                        for arm, targets in [("left", left_targets), ("right", right_targets)]:
                            if filtered[arm] is None:
                                with state_lock:
                                    real_pos = [real_joint_positions.get(j, targets[idx]) for idx, j in enumerate(JOINTS[arm])]
                                filtered[arm] = list(real_pos)
                            else:
                                for i in range(7):
                                    filtered[arm][i] = alpha * targets[i] + (1.0 - alpha) * filtered[arm][i]

                            # Suppress collision avoidance & publish position command
                            await ws.send(json.dumps({
                                "op": "publish",
                                "topic": f"/robot/limb/{arm}/suppress_collision_avoidance",
                                "msg": {}
                            }))
                            await ws.send(json.dumps({
                                "op": "publish",
                                "topic": f"/robot/limb/{arm}/joint_command",
                                "msg": {
                                    "mode": 1,
                                    "names": JOINTS[arm],
                                    "command": filtered[arm]
                                }
                            }))

                        # Head command
                        await ws.send(json.dumps({
                            "op": "publish",
                            "topic": "/robot/head/command_head_pan",
                            "msg": {
                                "target": float(head_target),
                                "speed_ratio": 0.5
                            }
                        }))

                        await asyncio.sleep(0.025) # 40 Hz command rate

            except Exception:
                await asyncio.sleep(1.5)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_sender())
    except Exception:
        pass


def udp_parallel_cmd_thread(port: int):
    """Background thread: Listens for zero-latency parallel joint commands from external scripts."""
    global sim_target_positions, running
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except Exception:
        return
    sock.setblocking(False)

    while running:
        ready = select.select([sock], [], [], 0.05)
        if ready[0]:
            try:
                data, _ = sock.recvfrom(4096)
                payload = json.loads(data.decode("utf-8"))
                
                # Support direct key action trigger
                if "key" in payload:
                    handle_key_action(payload["key"])

                # Support named pose trigger
                elif "pose" in payload:
                    pose_map = {"neutral": "1", "wave": "2", "boxing": "3", "cheer": "4", "reach": "5", "tuck": "0"}
                    pk = pose_map.get(str(payload["pose"]).lower())
                    if pk:
                        handle_key_action(pk)

                # Support explicit joint angles
                else:
                    names = payload.get("names", [])
                    cmd = payload.get("command", [])
                    with state_lock:
                        for n, c in zip(names, cmd):
                            sim_target_positions[n] = float(c)
            except Exception:
                pass


def setup_omniverse_keyboard():
    """Subscribes to Omniverse Kit 3D window keyboard events if available."""
    try:
        import omni.appwindow
        app_win = omni.appwindow.get_default_app_window()
        if not app_win:
            return None
        import carb.input
        input_iface = carb.input.acquire_input_interface()
        keyboard = app_win.get_keyboard()
        if not keyboard:
            return None

        KEY_MAP = {
            carb.input.KeyboardInput.KEY_1: '1',
            carb.input.KeyboardInput.KEY_2: '2',
            carb.input.KeyboardInput.KEY_3: '3',
            carb.input.KeyboardInput.KEY_4: '4',
            carb.input.KeyboardInput.KEY_5: '5',
            carb.input.KeyboardInput.KEY_0: '0',
            carb.input.KeyboardInput.TAB: '\t',
            carb.input.KeyboardInput.SPACE: ' ',
            carb.input.KeyboardInput.Q: 'q',
            carb.input.KeyboardInput.W: 'W',
            carb.input.KeyboardInput.E: 'e',
            carb.input.KeyboardInput.R: 'R',
            carb.input.KeyboardInput.T: 'T',
            carb.input.KeyboardInput.Y: 'y',
            carb.input.KeyboardInput.U: 'u',
            carb.input.KeyboardInput.S: 'S',
            carb.input.KeyboardInput.A: 'A',
            carb.input.KeyboardInput.D: 'D',
            carb.input.KeyboardInput.F: 'F',
            carb.input.KeyboardInput.G: 'G',
            carb.input.KeyboardInput.UP: '+',
            carb.input.KeyboardInput.DOWN: '-',
            carb.input.KeyboardInput.LEFT_BRACKET: '[',
            carb.input.KeyboardInput.RIGHT_BRACKET: ']',
            carb.input.KeyboardInput.C: 'c',
            carb.input.KeyboardInput.M: 'm',
            carb.input.KeyboardInput.H: 'h',
            carb.input.KeyboardInput.ESCAPE: 'x',
        }

        def on_key_event(event):
            if event.type == carb.input.KeyboardEventType.KEY_PRESS:
                ch = KEY_MAP.get(event.input)
                if ch:
                    handle_key_action(ch)
            return True

        sub = input_iface.subscribe_to_keyboard_events(keyboard, on_key_event)
        return sub
    except Exception:
        return None


def main():
    global running

    print_help_banner()

    # Configure Isaac Sim
    sim_cfg = sim_utils.SimulationCfg(
        device=args_cli.device,
        dt=0.0166, # 60 FPS physics
        render_interval=1
    )

    with launch_simulation(sim_cfg, args_cli):
        from isaaclab.assets import Articulation, ArticulationCfg
        from isaaclab.actuators import ImplicitActuatorCfg
        from isaaclab.sim import SimulationContext

        sim = SimulationContext(sim_cfg)

        # Set cinematic viewport camera: angled front-right isometric view of Baxter
        sim.set_camera_view(eye=[2.3, 1.8, 1.3], target=[0.0, 0.0, 0.65])

        # Environment: Studio ground and soft lighting
        cfg_ground = sim_utils.GroundPlaneCfg()
        cfg_ground.func("/World/defaultGroundPlane", cfg_ground)

        cfg_light = sim_utils.DomeLightCfg(intensity=2800.0, color=(0.92, 0.94, 1.0))
        cfg_light.func("/World/DomeLight", cfg_light)

        cfg_sun = sim_utils.DistantLightCfg(intensity=1800.0, color=(1.0, 0.98, 0.95), angle=0.53)
        cfg_sun.func("/World/SunLight", cfg_sun)

        # Baxter Articulation Definition
        baxter_usd_path = "/home/robotics/isaac/baxter.usd/baxter/baxter.usda"
        baxter_cfg = ArticulationCfg(
            prim_path="/World/Baxter",
            spawn=sim_utils.UsdFileCfg(usd_path=baxter_usd_path),
            actuators={
                "all_joints": ImplicitActuatorCfg(
                    joint_names_expr=[".*"],
                    stiffness=1500.0,
                    damping=80.0,
                )
            },
        )
        baxter = Articulation(cfg=baxter_cfg)
        sim.reset()

        # Joint index mapping
        joint_names = baxter.joint_names
        name_to_idx = {name: idx for idx, name in enumerate(joint_names)}

        # Allocate joint tensors on GPU
        joint_positions = torch.zeros((1, baxter.num_joints), device=sim.device)
        joint_velocities = torch.zeros((1, baxter.num_joints), device=sim.device)

        # Start background threads:
        # 1. Real-to-Sim joint state subscriber
        t_r2s = threading.Thread(target=rosbridge_real_to_sim_thread, args=(args_cli.host, args_cli.port), daemon=True)
        t_r2s.start()

        # 2. Sim-to-Real joint command publisher
        t_s2r = threading.Thread(target=rosbridge_sim_to_real_thread, args=(args_cli.host, args_cli.port), daemon=True)
        t_s2r.start()

        # 3. Terminal keyboard reader
        t_kbd = threading.Thread(target=terminal_keyboard_thread, daemon=True)
        t_kbd.start()

        # 4. Local UDP parallel listener
        t_udp = threading.Thread(target=udp_parallel_cmd_thread, args=(args_cli.udp_port,), daemon=True)
        t_udp.start()

        # 5. Omniverse Window keyboard subscriber (optional)
        kb_sub = setup_omniverse_keyboard()

        print("=" * 76)
        print("     🚀 BAXTER DIGITAL TWIN & REAL-TO-SIM / SIM-TO-REAL LIVE 🚀")
        print("=" * 76)
        print(f"  Physical Baxter: {args_cli.host}:{args_cli.port}")
        print(f"  Sim-to-Real:     {'ENABLED (Mirroring Sim -> Real)' if sim_to_real_enabled else 'DISABLED (Press [m] to toggle)'}")
        print(f"  Active Joints:   {len(baxter.joint_names)}")
        print("  Controls:        Type [1-5] for poses, [WASD] to move, [Tab] for other arm")
        print("=" * 76)

        frame_count = 0
        t_start = time.time()
        last_hud = t_start

        try:
            while sim.is_running() and running:
                with state_lock:
                    # In sim-to-real mode, keyboard/sim targets drive the simulation and robot
                    # In pure digital twin mode (sim-to-real disabled), physical encoders drive the simulation
                    if sim_to_real_enabled:
                        source = sim_target_positions
                    else:
                        source = real_joint_positions if real_joint_positions else sim_target_positions

                    for j_name, j_val in source.items():
                        if j_name in name_to_idx:
                            joint_positions[0, name_to_idx[j_name]] = float(j_val)

                # Write to PhysX in Isaac Sim
                baxter.write_joint_position_to_sim_index(position=joint_positions)
                baxter.write_joint_velocity_to_sim_index(velocity=joint_velocities)
                baxter.write_data_to_sim()

                # Step PhysX simulation and RTX render
                sim.step()
                baxter.update(sim.get_physics_dt())

                frame_count += 1
                now = time.time()
                if now - last_hud >= 1.5:
                    fps = frame_count / (now - t_start)
                    conn_str = "CONNECTED" if is_real_connected else "CONNECTING..."
                    s2r_str = "ACTIVE (Sim->Real)" if sim_to_real_enabled else "OFF (Sim Only)"
                    with state_lock:
                        curr_arm = active_arm.upper()
                        curr_j = JOINTS[active_arm][active_joint_idx]
                        curr_ang = sim_target_positions.get(curr_j, 0.0) * 57.2958
                        act = last_user_action

                    print(f"[*] FPS:{fps:4.1f} | Real:{conn_str:10s} | S2R:{s2r_str:18s} | Arm:{curr_arm} | {curr_j}:{curr_ang:+5.1f}° | {act}")
                    last_hud = now

        except KeyboardInterrupt:
            print("\n[*] Stopping Baxter Digital Twin...")
        finally:
            running = False


if __name__ == "__main__":
    main()
