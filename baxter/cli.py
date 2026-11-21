"""
Baxter CLI - Unified Command Line Interface for Rethink Robotics Baxter.
"""

import sys
import os
import math
import time
import asyncio
import argparse
from typing import Optional

from .client import Baxter, resolve_baxter_ip
from .poses import POSES, JOINTS
from .display import Display
from .choreography import SymphonyChoreography, DanceParty


def run_async(coro):
    """Convenience runner for async coroutines."""
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user.")
        sys.exit(0)


async def cmd_status(args):
    print("=" * 65)
    print("           BAXTER RESEARCH ROBOT - SYSTEM STATUS")
    print("=" * 65)
    ip = resolve_baxter_ip(args.host)
    print(f"Target Baxter Host: {ip} (ws://{ip}:{args.port})")

    async with Baxter(host=ip, port=args.port) as b:
        state = await b.get_state()
        if not state:
            print("[!] Unable to receive state from Baxter.")
            return

        en = state.get("enabled", False)
        st = state.get("stopped", False)
        err = state.get("error", False)
        rdy = state.get("ready", False)
        ebtn = state.get("estop_button", 0)

        print(f"Motors Enabled:   {'YES [POWER ON]' if en else 'NO [DISABLED]'}")
        print(f"Robot Stopped:    {'YES [STOPPED]' if st else 'NO [CLEARED]'}")
        print(f"System Ready:     {'YES' if rdy else 'NO'}")
        print(f"System Error:     {'YES [FAULT]' if err else 'NO [CLEAN]'}")
        print(f"E-Stop Button:    {'PRESSED [ACTIVE]' if ebtn else 'RELEASED [OK]'}")

        joints = await b.get_joint_positions()
        if joints:
            print("\nJoint Angles:")
            for arm in ("left", "right"):
                print(f"  {arm.upper()} ARM:")
                for j in JOINTS[arm]:
                    val = joints.get(j, 0.0)
                    print(f"    {j:12s}: {val:6.3f} rad ({math.degrees(val):6.1f}°)")
        print("=" * 65)


async def cmd_enable(args):
    async with Baxter(host=args.host, port=args.port) as b:
        print("[*] Sending Reset and Enable pulse...")
        ok = await b.enable()
        if ok:
            print("[✓] Baxter motors are successfully ENABLED!")
        else:
            print("[!] Failed to enable Baxter motors. Check E-Stop button.")


async def cmd_disable(args):
    async with Baxter(host=args.host, port=args.port) as b:
        print("[*] Disabling Baxter motors...")
        ok = await b.disable()
        if ok:
            print("[✓] Baxter motors DISABLED.")
        else:
            print("[!] State change did not reflect disable.")


async def cmd_reset(args):
    async with Baxter(host=args.host, port=args.port) as b:
        print("[*] Resetting Baxter fault states...")
        ok = await b.reset()
        if ok:
            print("[✓] Baxter faults cleared.")
        else:
            print("[!] Error state remains active.")


async def cmd_untuck(args):
    async with Baxter(host=args.host, port=args.port) as b:
        state = await b.get_state()
        if not state.get("enabled"):
            print("[!] Baxter is not enabled. Enabling motors first...")
            await b.enable()
        print("[*] Untucking arms to symmetrical neutral pose...")
        await b.untuck(duration=args.duration)
        print("[✓] Untuck complete.")


async def cmd_tuck(args):
    async with Baxter(host=args.host, port=args.port) as b:
        state = await b.get_state()
        if not state.get("enabled"):
            print("[!] Baxter is not enabled. Enabling motors first...")
            await b.enable()
        print("[*] Safely tucking arms into compact storage pose...")
        await b.tuck(duration=args.duration)
        print("[✓] Tuck complete.")


async def cmd_move(args):
    async with Baxter(host=args.host, port=args.port) as b:
        state = await b.get_state()
        if not state.get("enabled"):
            print("[!] Baxter is not enabled. Enabling motors first...")
            await b.enable()

        pose_name = args.pose.lower()
        if pose_name == "neutral":
            await b.untuck(duration=args.duration)
        elif pose_name == "wave":
            await b.wave()
        elif pose_name == "cheer":
            await b.cheer(duration=args.duration)
        elif pose_name == "salute":
            await b.salute(duration=args.duration)
        elif pose_name in POSES:
            pose = POSES[pose_name]
            await b.move_to(left=pose.get("left"), right=pose.get("right"), duration=args.duration)
        else:
            print(f"[!] Unknown pose '{pose_name}'. Available: neutral, wave, cheer, salute, reach, tuck")
            return
        print(f"[✓] Finished move: {pose_name}")


async def cmd_jog(args):
    async with Baxter(host=args.host, port=args.port) as b:
        limb_obj = b.left_arm if args.limb.lower() == "left" else b.right_arm
        print(f"[*] Jogging {args.limb} arm joint {args.joint} by {args.degrees:+.1f}°...")
        new_pos = await limb_obj.jog(args.joint, delta_deg=args.degrees, duration=args.duration)
        print(f"[✓] Jog complete. Current angle: {new_pos:.3f} rad ({math.degrees(new_pos):.1f}°)")


async def cmd_face(args):
    async with Baxter(host=args.host, port=args.port) as b:
        if args.image:
            print(f"[*] Loading and displaying image: {args.image}")
            await b.display.show_file(args.image)
            print("[✓] Image displayed.")
        else:
            emotion = args.emotion.lower()
            text = args.text or f"BAXTER | {emotion.upper()}"
            print(f"[*] Rendering face: emotion='{emotion}', text='{text}'")
            await b.display.show_emotion(emotion=emotion, status_text=text)
            print("[✓] Face updated on head display.")


async def cmd_head(args):
    async with Baxter(host=args.host, port=args.port) as b:
        if args.action == "pan":
            angle = math.radians(args.angle_deg) if args.degrees else args.angle
            print(f"[*] Panning head to {angle:.3f} rad...")
            await b.head.pan(angle, speed_ratio=args.speed)
            print("[✓] Head pan sent.")
        elif args.action == "nod":
            print("[*] Triggering head nod...")
            await b.head.nod()
            print("[✓] Nod sent.")


async def cmd_camera(args):
    async with Baxter(host=args.host, port=args.port) as b:
        cam_name = args.camera
        if args.action == "snapshot":
            out_file = args.output or f"baxter_{cam_name}.jpg"
            print(f"[*] Capturing frame from {cam_name}...")
            frame = await b.camera.read(cam_name, timeout=4.0)
            if frame is not None:
                import cv2
                cv2.imwrite(out_file, frame)
                print(f"[✓] Saved {frame.shape[1]}x{frame.shape[0]} snapshot to: {out_file}")
            else:
                print(f"[!] Failed to receive camera frame from {cam_name}.")
        elif args.action == "view":
            print(f"[*] Streaming {cam_name}. Press 'q' in window to exit...")
            import cv2
            async for frame in b.camera.stream(cam_name):
                cv2.imshow(f"Baxter Camera: {cam_name}", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cv2.destroyAllWindows()


async def cmd_dance(args):
    async with Baxter(host=args.host, port=args.port) as b:
        state = await b.get_state()
        if not state.get("enabled"):
            print("[!] Enabling Baxter motors...")
            await b.enable()
        dance = DanceParty(b)
        await dance.run(play_audio=not args.no_audio)


async def cmd_symphony(args):
    async with Baxter(host=args.host, port=args.port) as b:
        state = await b.get_state()
        if not state.get("enabled"):
            print("[!] Enabling Baxter motors...")
            await b.enable()
        symphony = SymphonyChoreography(b)
        await symphony.run()


async def cmd_box(args):
    from .vision import BoxerSparring
    cam_src = int(args.camera) if str(args.camera).isdigit() else args.camera
    async with Baxter(host=args.host, port=args.port) as b:
        state = await b.get_state()
        if not state.get("enabled"):
            print("[!] Enabling Baxter motors...")
            await b.enable()
        boxer = BoxerSparring(b, camera_source=cam_src, show_gui=not args.no_gui, verbose=not args.quiet)
        await boxer.run(duration_sec=args.duration)


async def cmd_play(args):
    from .arena import InteractiveArena
    cam_src = int(args.camera) if str(args.camera).isdigit() else args.camera
    async with Baxter(host=args.host, port=args.port) as b:
        state = await b.get_state()
        if not state.get("enabled"):
            print("[!] Enabling Baxter motors...")
            await b.enable()
        arena = InteractiveArena(b, camera_source=cam_src, mirror=not args.no_mirror, show_gui=not args.no_gui)
        await arena.run(duration_sec=args.duration)


def cmd_sim(args):
    from .sim import launch_sim_twin
    ip = resolve_baxter_ip(args.host)
    launch_sim_twin(
        host=ip,
        port=args.port,
        udp_port=args.udp_port,
        headless=args.headless,
        sim_to_real=args.sim_to_real,
        screenshot=args.screenshot,
        pose=args.pose
    )


def main():
    parser = argparse.ArgumentParser(
        prog="baxter",
        description="Baxter-Py CLI: Native ROS-agnostic control suite for Rethink Robotics Baxter"
    )
    parser.add_argument("--host", default=None, help="Baxter IP address or hostname (default: auto-detect)")
    parser.add_argument("--port", type=int, default=9090, help="Rosbridge WebSocket port (default: 9090)")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # status
    p_status = subparsers.add_parser("status", help="Show robot state, safety interlocks, and joint angles")

    # enable / disable / reset
    p_enable = subparsers.add_parser("enable", help="Reset fault state and enable robot arm motors")
    p_disable = subparsers.add_parser("disable", help="Disable robot arm motors")
    p_reset = subparsers.add_parser("reset", help="Clear error and fault flags")

    # untuck / tuck
    p_untuck = subparsers.add_parser("untuck", help="Move arms to symmetrical operational neutral pose")
    p_untuck.add_argument("--duration", type=float, default=4.0, help="Trajectory duration in seconds")

    p_tuck = subparsers.add_parser("tuck", help="Fold arms safely into compact shipping/storage pose")
    p_tuck.add_argument("--duration", type=float, default=5.0, help="Trajectory duration in seconds")

    # move
    p_move = subparsers.add_parser("move", help="Move arms to a standard pose")
    p_move.add_argument("pose", choices=["neutral", "wave", "cheer", "salute", "reach", "tuck"], help="Pose name")
    p_move.add_argument("--duration", type=float, default=3.5, help="Motion duration in seconds")

    # jog
    p_jog = subparsers.add_parser("jog", help="Jog a single joint by delta degrees")
    p_jog.add_argument("limb", choices=["left", "right"], help="Limb name")
    p_jog.add_argument("joint", help="Joint name (s0, s1, e0, e1, w0, w1, w2)")
    p_jog.add_argument("degrees", type=float, help="Delta angle in degrees (e.g. 10.0 or -15.0)")
    p_jog.add_argument("--duration", type=float, default=2.0, help="Jog duration in seconds")

    # face
    p_face = subparsers.add_parser("face", help="Render stylized vector face or image to head display")
    p_face.add_argument("emotion", nargs="?", default="neutral",
                        choices=["neutral", "happy", "focused", "wink", "disco", "boxing", "sleepy", "surprised"],
                        help="Face emotion")
    p_face.add_argument("--text", default=None, help="Custom status banner text")
    p_face.add_argument("--image", default=None, help="Display image file directly")

    # head
    p_head = subparsers.add_parser("head", help="Control head pan angle or nod")
    head_sub = p_head.add_subparsers(dest="action", required=True)
    p_pan = head_sub.add_parser("pan", help="Pan head to target angle")
    p_pan.add_argument("angle", type=float, help="Target angle (default: radians)")
    p_pan.add_argument("--deg", dest="degrees", action="store_true", help="Specify angle in degrees")
    p_pan.add_argument("--speed", type=float, default=0.5, help="Speed ratio (0.1 to 1.0)")
    p_nod = head_sub.add_parser("nod", help="Perform head nod gesture")

    # camera
    p_cam = subparsers.add_parser("camera", help="Inspect onboard cameras")
    p_cam.add_argument("--camera", default="head_camera", choices=["head_camera", "left_hand_camera", "right_hand_camera"])
    cam_sub = p_cam.add_subparsers(dest="action", required=True)
    p_snap = cam_sub.add_parser("snapshot", help="Save a still image frame to disk")
    p_snap.add_argument("-o", "--output", default=None, help="Output image file path")
    p_view = cam_sub.add_parser("view", help="View live video stream in OpenCV window")

    # dance
    p_dance = subparsers.add_parser("dance", help="Run 124 BPM Daft Punk style musical dance routine")
    p_dance.add_argument("--no-audio", action="store_true", help="Disable backing audio playback")

    # symphony
    p_symphony = subparsers.add_parser("symphony", help="Run 5-act orchestral symphony choreography")

    # box
    p_box = subparsers.add_parser("box", help="Run interactive MediaPipe boxing sparring partner")
    p_box.add_argument("--duration", type=float, default=60.0, help="Sparring round duration in seconds")
    p_box.add_argument("--camera", "--cam", default="auto", help="Camera source: 0 for USB external webcam, head for Baxter head cam (default: auto)")
    p_box.add_argument("--no-gui", action="store_true", help="Run in headless mode without opening OpenCV visual feed")
    p_box.add_argument("--quiet", action="store_true", help="Suppress real-time terminal diagnostic logs")

    # play / arena
    p_play = subparsers.add_parser("play", help="Launch Baxter Interactive Arena (Rock-Paper-Scissors, Boxer 2.0, Jedi Teleop, Fist-Bump)")
    p_play.add_argument("--duration", type=float, default=300.0, help="Session duration in seconds (default: 300)")
    p_play.add_argument("--camera", "--cam", default="auto", help="Camera source: 0 for USB external webcam, head for Baxter head cam (default: auto)")
    p_play.add_argument("--no-mirror", action="store_true", help="Disable selfie mirror reflection mode")
    p_play.add_argument("--no-gui", action="store_true", help="Run in headless mode without desktop OpenCV window")

    p_arena = subparsers.add_parser("arena", help="Alias for 'play'")
    p_arena.add_argument("--duration", type=float, default=300.0, help="Session duration in seconds (default: 300)")
    p_arena.add_argument("--camera", "--cam", default="auto", help="Camera source: 0 for USB external webcam, head for Baxter head cam (default: auto)")
    p_arena.add_argument("--no-mirror", action="store_true", help="Disable selfie mirror reflection mode")
    p_arena.add_argument("--no-gui", action="store_true", help="Run in headless mode without desktop OpenCV window")

    # sim
    p_sim = subparsers.add_parser("sim", help="Launch NVIDIA Isaac Sim Baxter 3D Digital Twin with real-to-sim / sim-to-real bridge")
    p_sim.add_argument("--headless", action="store_true", help="Run in headless mode without opening GUI window")
    p_sim.add_argument("--udp-port", type=int, default=19888, help="Local UDP parallel command port (default: 19888)")
    p_sim.add_argument("--sim-to-real", action="store_true", help="Enable commanding physical robot from simulation")
    p_sim.add_argument("--screenshot", default=None, help="Capture RTX photorealistic screenshot to file and exit")
    p_sim.add_argument("--pose", default="neutral", choices=["neutral", "wave", "boxing", "hero"], help="Robot pose for screenshot (default: neutral)")

    args = parser.parse_args()

    dispatch = {
        "status": cmd_status,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "reset": cmd_reset,
        "untuck": cmd_untuck,
        "tuck": cmd_tuck,
        "move": cmd_move,
        "jog": cmd_jog,
        "face": cmd_face,
        "head": cmd_head,
        "camera": cmd_camera,
        "dance": cmd_dance,
        "symphony": cmd_symphony,
        "box": cmd_box,
        "play": cmd_play,
        "arena": cmd_play,
        "sim": cmd_sim,
    }

    fn = dispatch.get(args.command)
    if fn:
        import inspect
        if inspect.iscoroutinefunction(fn):
            run_async(fn(args))
        else:
            fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
