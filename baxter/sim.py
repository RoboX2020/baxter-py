"""
Baxter Isaac Sim Digital Twin & Bidirectional Synchronization Module.
Connects Rethink Robotics Baxter to NVIDIA Isaac Sim / IsaacLab.
"""

import os
import sys
import json
import socket
import shutil
import subprocess
from typing import List, Optional


DEFAULT_ISAAC_LAB_DIR = os.environ.get("ISAACLAB_PATH", "/home/robotics/isaac/IsaacLab")
DEFAULT_TWIN_SCRIPT = os.path.join(os.path.dirname(DEFAULT_ISAAC_LAB_DIR), "isaac_baxter_twin.py")
DEFAULT_RENDER_SCRIPT = os.path.join(os.path.dirname(DEFAULT_ISAAC_LAB_DIR), "render_isaac_baxter_showcase.py")
GOMP_LIB = "/lib/aarch64-linux-gnu/libgomp.so.1"


def get_isaac_python() -> Optional[str]:
    """Finds python executable capable of running Isaac Sim / IsaacLab."""
    venv_py = os.path.join(DEFAULT_ISAAC_LAB_DIR, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        return venv_py
    return None


def get_uv_path() -> Optional[str]:
    """Finds uv binary path."""
    which_uv = shutil.which("uv")
    if which_uv:
        return which_uv
    candidate = os.path.expanduser("~/.local/bin/uv")
    if os.path.exists(candidate):
        return candidate
    return None


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


def render_screenshot(
    output_path: str,
    pose: str = "neutral",
    width: int = 1920,
    height: int = 1080
) -> int:
    """
    Renders a photorealistic RTX viewport screenshot of Baxter in Isaac Sim.
    """
    isaac_py = get_isaac_python()
    if not isaac_py:
        print(f"[!] IsaacLab python environment not found at {DEFAULT_ISAAC_LAB_DIR}/.venv")
        return 1

    env = os.environ.copy()
    if os.path.exists(GOMP_LIB):
        env["LD_PRELOAD"] = GOMP_LIB

    # Inline render script to guarantee zero external file dependency
    render_code = f"""
from isaacsim import SimulationApp
app = SimulationApp({{"headless": True, "width": {width}, "height": {height}}})

import os, omni.usd, omni.timeline
import omni.kit.viewport.utility as vp_util
from pxr import UsdGeom, Gf, UsdLux

stage = omni.usd.get_context().get_stage()

# Studio Lights
dlight = UsdLux.DomeLight.Define(stage, '/World/DomeLight')
dlight.CreateIntensityAttr(2600.0)
dlight.CreateColorAttr(Gf.Vec3f(0.95, 0.96, 1.0))

sun = UsdLux.DistantLight.Define(stage, '/World/SunLight')
sun.CreateIntensityAttr(2200.0)
sun.CreateColorAttr(Gf.Vec3f(1.0, 0.98, 0.92))
UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(-40.0, 35.0, 0.0))

# Baxter USD
baxter = stage.DefinePrim('/World/Baxter', 'Xform')
baxter.GetReferences().AddReference('/home/robotics/isaac/baxter.usd/baxter/baxter.usda')

# Camera
cam_prim = stage.DefinePrim('/World/RenderCam', 'Camera')
cam_geom = UsdGeom.Camera(cam_prim)
cam_geom.CreateFocalLengthAttr(26.0)
xformable = UsdGeom.Xformable(cam_prim)

vp = vp_util.get_active_viewport()
if vp:
    vp.set_active_camera('/World/RenderCam')

POSES = {{
    "neutral": {{
        "angles": {{
            "head_pan": 0.0,
            "left_s0": -5.0, "left_s1": -55.0, "left_e0": -70.0, "left_e1": 110.0, "left_w0": 40.0, "left_w1": 60.0, "left_w2": -30.0,
            "right_s0": 5.0, "right_s1": -55.0, "right_e0": 70.0, "right_e1": 110.0, "right_w0": -40.0, "right_w1": 60.0, "right_w2": 30.0
        }},
        "eye": Gf.Vec3d(2.6, 2.0, 1.2),
        "target": Gf.Vec3d(0.0, 0.0, 0.55),
    }},
    "wave": {{
        "angles": {{
            "head_pan": 18.0,
            "left_s0": -5.0, "left_s1": -55.0, "left_e0": -70.0, "left_e1": 110.0, "left_w0": 40.0, "left_w1": 60.0, "left_w2": -30.0,
            "right_s0": 25.0, "right_s1": -40.0, "right_e0": 20.0, "right_e1": 115.0, "right_w0": 10.0, "right_w1": -25.0, "right_w2": 20.0
        }},
        "eye": Gf.Vec3d(2.3, 1.5, 1.2),
        "target": Gf.Vec3d(0.0, 0.0, 0.65),
    }},
    "boxing": {{
        "angles": {{
            "head_pan": -5.0,
            "left_s0": -15.0, "left_s1": -35.0, "left_e0": -30.0, "left_e1": 115.0, "left_w0": 25.0, "left_w1": 25.0, "left_w2": -15.0,
            "right_s0": 15.0, "right_s1": -20.0, "right_e0": 10.0, "right_e1": 60.0, "right_w0": 0.0, "right_w1": 10.0, "right_w2": 0.0
        }},
        "eye": Gf.Vec3d(2.4, -1.8, 1.2),
        "target": Gf.Vec3d(0.0, 0.0, 0.60),
    }},
    "hero": {{
        "angles": {{
            "head_pan": 0.0,
            "left_s0": -35.0, "left_s1": -30.0, "left_e0": -20.0, "left_e1": 45.0, "left_w0": 0.0, "left_w1": 0.0, "left_w2": 0.0,
            "right_s0": 35.0, "right_s1": -30.0, "right_e0": 20.0, "right_e1": 45.0, "right_w0": 0.0, "right_w1": 0.0, "right_w2": 0.0
        }},
        "eye": Gf.Vec3d(2.7, 0.0, 1.1),
        "target": Gf.Vec3d(0.0, 0.0, 0.55),
    }}
}}

cfg = POSES.get('{pose.lower()}', POSES['neutral'])
cam_xform = Gf.Matrix4d().SetLookAt(cfg['eye'], cfg['target'], Gf.Vec3d(0.0, 0.0, 1.0)).GetInverse()
xformable.ClearXformOpOrder()
xformable.AddTransformOp().Set(cam_xform)

timeline = omni.timeline.get_timeline_interface()
timeline.play()

for j_name, deg in cfg['angles'].items():
    prim = stage.GetPrimAtPath(f'/World/Baxter/Physics/{{j_name}}')
    if prim.IsValid():
        attr = prim.GetAttribute('drive:angular:physics:targetPosition')
        if attr.IsValid():
            attr.Set(float(deg))
        stiff = prim.GetAttribute('drive:angular:physics:stiffness')
        if stiff.IsValid():
            stiff.Set(5000.0)
        damp = prim.GetAttribute('drive:angular:physics:damping')
        if damp.IsValid():
            damp.Set(200.0)

for _ in range(50):
    app.update()

out_path = '{os.path.abspath(output_path)}'
os.makedirs(os.path.dirname(out_path), exist_ok=True)
vp_util.capture_viewport_to_file(vp, file_path=out_path)

for _ in range(25):
    app.update()

timeline.stop()
app.close()
if os.path.exists(out_path):
    print(f'[✓] Successfully rendered RTX screenshot: {{out_path}} ({{os.path.getsize(out_path)}} bytes)')
else:
    print('[!] Viewport capture failed.')
"""

    print("=" * 70)
    print("      📸 RENDERING PHOTOREALISTIC BAXTER SCREENSHOT 📸")
    print("=" * 70)
    print(f"  Pose:        {pose}")
    print(f"  Resolution:  {width}x{height}")
    print(f"  Output:      {output_path}")
    print("=" * 70)

    proc = subprocess.run([isaac_py, "-c", render_code], env=env)
    return proc.returncode


def launch_sim_twin(
    host: str = "169.254.127.243",
    port: int = 9090,
    udp_port: int = 19888,
    headless: bool = False,
    sim_to_real: bool = False,
    screenshot: Optional[str] = None,
    pose: str = "neutral"
):
    """
    Launches Isaac Sim with Baxter Digital Twin in a configured environment.
    """
    if screenshot:
        return render_screenshot(output_path=screenshot, pose=pose)

    if not os.path.exists(DEFAULT_ISAAC_LAB_DIR):
        print(f"[!] IsaacLab directory not found at {DEFAULT_ISAAC_LAB_DIR}")
        return 1

    if not os.path.exists(DEFAULT_TWIN_SCRIPT):
        print(f"[!] Baxter twin script not found at {DEFAULT_TWIN_SCRIPT}")
        return 1

    env = os.environ.copy()
    if os.path.exists(GOMP_LIB):
        env["LD_PRELOAD"] = GOMP_LIB

    # Resolve Display
    if not headless:
        if "DISPLAY" not in env or not env["DISPLAY"]:
            # Check available X11 sockets
            if os.path.exists("/tmp/.X11-unix/X1"):
                env["DISPLAY"] = ":1"
            elif os.path.exists("/tmp/.X11-unix/X0"):
                env["DISPLAY"] = ":0"
            else:
                print("[!] No active X11 display detected. Switching to headless mode.")
                headless = True

    # Build command line
    isaac_py = get_isaac_python()
    uv_bin = get_uv_path()

    if uv_bin:
        cmd = [
            uv_bin, "run", "python", DEFAULT_TWIN_SCRIPT,
            "--host", host,
            "--port", str(port),
            "--udp-port", str(udp_port),
        ]
    elif isaac_py:
        cmd = [
            isaac_py, DEFAULT_TWIN_SCRIPT,
            "--host", host,
            "--port", str(port),
            "--udp-port", str(udp_port),
        ]
    else:
        print("[!] Neither uv nor IsaacLab python environment found.")
        return 1

    if headless:
        cmd.append("--headless")
    if sim_to_real:
        cmd.append("--sim-to-real")

    print("=" * 70)
    print("      🚀 LAUNCHING NVIDIA ISAAC SIM - BAXTER DIGITAL TWIN 🚀")
    print("=" * 70)
    print(f"  IsaacLab Path:  {DEFAULT_ISAAC_LAB_DIR}")
    print(f"  Physical Robot: {host}:{port}")
    print(f"  Display Target: {env.get('DISPLAY', 'NONE (HEADLESS)')}")
    print(f"  Mode:           {'Headless Simulation' if headless else 'Interactive 3D Viewport'}")
    print(f"  Sim-to-Real:    {'ENABLED' if sim_to_real else 'Disabled (Sim-Only)'}")
    print(f"  Command:        {' '.join(cmd)}")
    print("=" * 70)

    try:
        proc = subprocess.Popen(cmd, cwd=DEFAULT_ISAAC_LAB_DIR, env=env)
        return proc.wait()
    except KeyboardInterrupt:
        print("\n[*] Stopping Isaac Sim Digital Twin...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 0
