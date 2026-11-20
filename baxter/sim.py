"""
Baxter Isaac Sim Digital Twin & Bidirectional Synchronization Module.
Connects Rethink Robotics Baxter to NVIDIA Isaac Sim / IsaacLab.
"""

import os
import sys
import json
import socket
import subprocess
from typing import List, Optional


ISAAC_LAB_DIR = "/home/robotics/isaac/IsaacLab"
TWIN_SCRIPT_PATH = "/home/robotics/isaac/isaac_baxter_twin.py"
GOMP_LIB = "/lib/aarch64-linux-gnu/libgomp.so.1"


def broadcast_sim_command(names: List[str], command: List[float], port: int = 19888):
    """Broadcasts joint position targets to local Isaac Sim bridge via UDP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        payload = json.dumps({"names": names, "command": command}).encode("utf-8")
        sock.sendto(payload, ("127.0.0.1", port))
        sock.close()
    except Exception:
        pass


def launch_sim_twin(
    host: str = "169.254.127.243",
    port: int = 9090,
    udp_port: int = 19888,
    headless: bool = False,
    sim_to_real: bool = False
):
    """
    Launches Isaac Sim with Baxter Digital Twin in a configured environment.
    """
    if not os.path.exists(ISAAC_LAB_DIR):
        print(f"[!] IsaacLab directory not found at {ISAAC_LAB_DIR}")
        return 1

    if not os.path.exists(TWIN_SCRIPT_PATH):
        print(f"[!] Baxter twin script not found at {TWIN_SCRIPT_PATH}")
        return 1

    env = os.environ.copy()
    if os.path.exists(GOMP_LIB):
        env["LD_PRELOAD"] = GOMP_LIB

    if headless:
        env["HEADLESS"] = "1"
    else:
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":1"

    cmd = [
        "uv", "run", "python", TWIN_SCRIPT_PATH,
        "--host", host,
        "--port", str(port),
        "--udp-port", str(udp_port),
    ]
    if sim_to_real:
        cmd.append("--sim-to-real")

    print("=" * 70)
    print("      🚀 LAUNCHING NVIDIA ISAAC SIM - BAXTER DIGITAL TWIN 🚀")
    print("=" * 70)
    print(f"  IsaacLab Path:  {ISAAC_LAB_DIR}")
    print(f"  Physical Robot: {host}:{port}")
    print(f"  Display Target: {env.get('DISPLAY', 'HEADLESS')}")
    print(f"  Mode:           {'Headless' if headless else 'Interactive 3D Viewport'}")
    print("=" * 70)

    try:
        proc = subprocess.Popen(cmd, cwd=ISAAC_LAB_DIR, env=env)
        return proc.wait()
    except KeyboardInterrupt:
        print("\n[*] Stopping Isaac Sim Digital Twin...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 0
