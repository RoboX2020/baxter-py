#!/usr/bin/env python3
"""
3D Fingertip Spatial Tracker & Baxter Sim-to-Real Teleoperation System.
Uses monocular camera to map the user's index fingertip in 3D metric space (X, Y, Z in meters)
and streams 3D motion in real-time to NVIDIA Isaac Sim and the physical Baxter robot.
"""

import os
import sys
import time
import math
import json
import socket
import collections
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Default model path
MODEL_PATH = "/home/robotics/models/gesture_recognizer.task"
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = "/home/robotics/baxter-py/models/gesture_recognizer.task"

UDP_PORT = 19888
UDP_IP = "127.0.0.1"

# Baxter Neutral joint baselines
NEUTRAL_ARM = {
    'right': [0.08, -1.00, 1.19, 1.94, -0.67, 1.03, 0.50],
    'left':  [-0.08, -1.00, -1.19, 1.94, 0.67, 1.03, -0.50]
}

JOINTS = {
    'right': ['right_s0', 'right_s1', 'right_e0', 'right_e1', 'right_w0', 'right_w1', 'right_w2'],
    'left':  ['left_s0', 'left_s1', 'left_e0', 'left_e1', 'left_w0', 'left_w1', 'left_w2']
}

LIMITS = {
    's0': (-1.701, 1.701),
    's1': (-2.147, 1.047),
    'e0': (-3.054, 3.054),
    'e1': (-0.050, 2.618),
    'w0': (-3.059, 3.059),
    'w1': (-1.571, 2.094),
    'w2': (-3.059, 3.059),
}

# MediaPipe Hand Connections
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # Index
    (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
    (9, 13), (13, 14), (14, 15), (15, 16), # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
    (0, 17)                                # Palm base
]


class Fingertip3DTracker:
    def __init__(self, camera_id: int = 0, udp_port: int = UDP_PORT):
        self.camera_id = camera_id
        self.udp_port = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

        # Initialize MediaPipe Gesture / Hand Recognizer
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=1
        )
        self.recognizer = vision.GestureRecognizer.create_from_options(options)

        # Tracking state
        self.active_arm = "right"
        self.continuous_mode = True # Always track vs Pinch to engage
        self.origin_3d: Optional[np.ndarray] = None # Calibrated center (X, Y, Z)
        self.current_3d: Optional[np.ndarray] = None
        self.trail_3d = collections.deque(maxlen=40)
        self.trail_2d = collections.deque(maxlen=40)

        # Filtered arm angles
        self.filtered_arm = list(NEUTRAL_ARM[self.active_arm])
        self.alpha = 0.22 # Low-pass filter weight

        # Sensitivity gains (radians per meter)
        self.gain_x = 1.9 # Horizontal sweep (s0)
        self.gain_y = 2.2 # Vertical elevation (s1)
        self.gain_z = 1.8 # Reach / elbow extension (e1)

        # Performance stats
        self.fps = 0.0
        self.last_time = time.time()
        self.frame_count = 0

    def compute_3d_coordinates(self, landmarks, img_w: int, img_h: int) -> Tuple[np.ndarray, bool]:
        """
        Computes metric 3D position (X, Y, Z) in meters of index fingertip (landmark 8).
        Uses perspective projection model with metric knuckle width scale.
        """
        tip = landmarks[8]
        idx_mcp = landmarks[5]
        pky_mcp = landmarks[17]
        thumb_tip = landmarks[4]

        # Pixel positions
        u_tip = tip.x * img_w
        v_tip = tip.y * img_h
        u5, v5 = idx_mcp.x * img_w, idx_mcp.y * img_h
        u17, v17 = pky_mcp.x * img_w, pky_mcp.y * img_h

        # Knuckle pixel width
        knuckle_px = max(12.0, math.hypot(u5 - u17, v5 - v17))

        # Standard 60 deg horizontal FOV focal length: fx = (W/2) / tan(30 deg)
        fx = (img_w / 2.0) / math.tan(math.radians(30.0))
        fy = fx

        # Knuckle metric reference width: average adult knuckle span is 7.5 cm (0.075 m)
        K_WIDTH_M = 0.075
        z_m = (fx * K_WIDTH_M) / knuckle_px
        z_m = max(0.20, min(1.40, z_m)) # Clamp depth to 20 cm - 140 cm

        # Metric X, Y relative to camera optical center
        cx, cy = img_w / 2.0, img_h / 2.0
        x_m = ((u_tip - cx) * z_m) / fx
        y_m = ((v_tip - cy) * z_m) / fy

        # Pinch detection (distance between thumb tip #4 and index fingertip #8)
        u4, v4 = thumb_tip.x * img_w, thumb_tip.y * img_h
        pinch_dist = math.hypot(u4 - u_tip, v4 - v_tip)
        is_pinched = pinch_dist < (knuckle_px * 0.40)

        coord_3d = np.array([x_m, y_m, z_m], dtype=np.float32)
        return coord_3d, is_pinched

    def map_to_baxter_joints(self, pos_3d: np.ndarray) -> List[float]:
        """Maps relative 3D movement (delta X, Y, Z) to 7-DOF Baxter arm joint angles."""
        if self.origin_3d is None:
            self.origin_3d = pos_3d.copy()

        # Delta in meters from calibrated origin
        dx = pos_3d[0] - self.origin_3d[0]
        dy = -(pos_3d[1] - self.origin_3d[1]) # Up is positive in 3D
        dz = -(pos_3d[2] - self.origin_3d[2]) # Forward (closer) is positive reach

        neutral = NEUTRAL_ARM[self.active_arm]
        target = list(neutral)

        # Shoulder pan (s0): Horizontal sweep
        # For right arm: positive dx sweeps outward (positive s0)
        # For left arm: negative dx sweeps outward (negative s0)
        s0_sign = 1.0 if self.active_arm == "right" else 1.0
        target[0] = max(LIMITS['s0'][0], min(LIMITS['s0'][1], neutral[0] + s0_sign * self.gain_x * dx))

        # Shoulder pitch (s1): Vertical elevation (moving hand UP raises arm)
        target[1] = max(LIMITS['s1'][0], min(LIMITS['s1'][1], neutral[1] + self.gain_y * dy))

        # Elbow pitch (e1): Forward reach (pushing forward flexes/extends elbow)
        target[3] = max(LIMITS['e1'][0], min(LIMITS['e1'][1], neutral[3] - self.gain_z * dz))

        # Smooth low-pass filtering
        for i in range(7):
            self.filtered_arm[i] = self.alpha * target[i] + (1.0 - self.alpha) * self.filtered_arm[i]

        return self.filtered_arm

    def send_sim_to_real_command(self, joint_angles: List[float]):
        """Transmits joint angles to local Isaac Sim Sim-to-Real bridge via UDP."""
        try:
            payload = {
                "names": JOINTS[self.active_arm],
                "command": [float(a) for a in joint_angles]
            }
            self.sock.sendto(json.dumps(payload).encode("utf-8"), (UDP_IP, self.udp_port))
        except Exception:
            pass

    def draw_3d_workspace_isometric(self, width: int = 340, height: int = 480) -> np.ndarray:
        """
        Renders an isometric 3D spatial viewport visualizing the fingertip position,
        bounding workspace box, and 3D trajectory trail.
        """
        vis = np.zeros((height, width, 3), dtype=np.uint8)
        vis[:] = (20, 24, 30) # Dark futuristic background

        # Header
        cv2.putText(vis, "3D SPATIAL WORKSPACE", (15, 28), cv2.FONT_HERSHEY_DUPLEX, 0.60, (0, 230, 255), 1, cv2.LINE_AA)
        cv2.line(vis, (15, 36), (width - 15, 36), (60, 70, 85), 1)

        # Isometric projection parameters
        origin_screen = np.array([width // 2, 260], dtype=np.float32)
        scale_x = 180.0
        scale_y = 120.0
        scale_z = 150.0

        def project_iso(x: float, y: float, z: float) -> Tuple[int, int]:
            # Simple isometric projection
            iso_u = origin_screen[0] + (x * 0.866 - z * 0.866) * scale_x
            iso_v = origin_screen[1] - y * scale_y + (x * 0.5 + z * 0.5) * 60.0
            return int(iso_u), int(iso_v)

        # Draw 3D bounding box (representing reachable space: X in [-0.3, 0.3], Y in [-0.3, 0.3], Z in [-0.3, 0.3])
        box_corners = [
            (-0.25, -0.20, -0.25), (0.25, -0.20, -0.25),
            (0.25, 0.20, -0.25), (-0.25, 0.20, -0.25),
            (-0.25, -0.20, 0.25), (0.25, -0.20, 0.25),
            (0.25, 0.20, 0.25), (-0.25, 0.20, 0.25),
        ]
        proj_pts = [project_iso(c[0], c[1], c[2]) for c in box_corners]

        # Draw bottom ground grid
        ground_pts = np.array([proj_pts[0], proj_pts[1], proj_pts[5], proj_pts[4]], dtype=np.int32)
        cv2.fillPoly(vis, [ground_pts], (28, 33, 42))
        cv2.polylines(vis, [ground_pts], True, (60, 75, 95), 1, cv2.LINE_AA)

        # Wireframe box lines
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        for e in edges:
            cv2.line(vis, proj_pts[e[0]], proj_pts[e[1]], (45, 55, 70), 1, cv2.LINE_AA)

        # Coordinate axes
        p_o = project_iso(0, 0, 0)
        p_x = project_iso(0.18, 0, 0)
        p_y = project_iso(0, 0.18, 0)
        p_z = project_iso(0, 0, 0.18)
        cv2.line(vis, p_o, p_x, (0, 0, 220), 2, cv2.LINE_AA) # X = Red
        cv2.line(vis, p_o, p_y, (0, 220, 0), 2, cv2.LINE_AA) # Y = Green
        cv2.line(vis, p_o, p_z, (220, 150, 0), 2, cv2.LINE_AA) # Z = Blue
        cv2.putText(vis, "X", (p_x[0] + 4, p_x[1]), cv2.FONT_HERSHEY_PLAIN, 0.8, (0, 0, 255), 1)
        cv2.putText(vis, "Y", (p_y[0], p_y[1] - 4), cv2.FONT_HERSHEY_PLAIN, 0.8, (0, 255, 0), 1)
        cv2.putText(vis, "Z", (p_z[0] + 4, p_z[1]), cv2.FONT_HERSHEY_PLAIN, 0.8, (255, 180, 0), 1)

        # Draw 3D Trajectory Trail
        if self.origin_3d is not None and len(self.trail_3d) > 1:
            pts_iso = []
            for p in self.trail_3d:
                rel = p - self.origin_3d
                pts_iso.append(project_iso(rel[0], -rel[1], -rel[2]))
            for i in range(len(pts_iso) - 1):
                fade = (i + 1) / len(pts_iso)
                color = (int(0 * fade), int(255 * fade), int(255 * fade))
                cv2.line(vis, pts_iso[i], pts_iso[i+1], color, max(1, int(3 * fade)), cv2.LINE_AA)

        # Draw Current Fingertip Point in 3D
        if self.current_3d is not None and self.origin_3d is not None:
            rel = self.current_3d - self.origin_3d
            p_tip = project_iso(rel[0], -rel[1], -rel[2])
            # Drop shadow on ground (y = -0.20)
            p_shadow = project_iso(rel[0], -0.20, -rel[2])
            cv2.line(vis, p_tip, p_shadow, (40, 80, 100), 1, cv2.LINE_AA)
            cv2.circle(vis, p_shadow, 4, (30, 80, 80), -1)

            # Glowing tip sphere
            cv2.circle(vis, p_tip, 8, (0, 200, 255), -1, cv2.LINE_AA)
            cv2.circle(vis, p_tip, 12, (0, 255, 255), 1, cv2.LINE_AA)

        # Telemetry Text Block
        y_text = 360
        cv2.line(vis, (15, y_text - 12), (width - 15, y_text - 12), (50, 60, 75), 1)
        cv2.putText(vis, "3D METRIC TELEMETRY", (15, y_text), cv2.FONT_HERSHEY_DUPLEX, 0.48, (200, 210, 225), 1)

        if self.current_3d is not None:
            x_m, y_m, z_m = self.current_3d
            cv2.putText(vis, f"X (Lateral)  : {x_m:+0.3f} m", (20, y_text + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            cv2.putText(vis, f"Y (Vertical) : {-y_m:+0.3f} m", (20, y_text + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 180), 1)
            cv2.putText(vis, f"Z (Depth)    : {z_m:0.3f} m", (20, y_text + 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 0), 1)
        else:
            cv2.putText(vis, "Hand Not Detected", (20, y_text + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 145), 1)

        # Joint angle bars
        cv2.putText(vis, f"BAXTER {self.active_arm.upper()} ARM:", (15, y_text + 80), cv2.FONT_HERSHEY_DUPLEX, 0.45, (220, 225, 235), 1)
        s0_deg = self.filtered_arm[0] * 57.2958
        s1_deg = self.filtered_arm[1] * 57.2958
        e1_deg = self.filtered_arm[3] * 57.2958
        cv2.putText(vis, f"s0 (pan): {s0_deg:+5.1f} deg | s1 (pitch): {s1_deg:+5.1f} deg", (20, y_text + 96), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 200), 1)
        cv2.putText(vis, f"e1 (elbow): {e1_deg:+5.1f} deg | FPS: {self.fps:4.1f}", (20, y_text + 112), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 190, 200), 1)

        return vis

    def run(self):
        """Main real-time tracking loop."""
        cap = cv2.VideoCapture(self.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap.isOpened():
            print(f"[!] Error: Could not open camera {self.camera_id}")
            return

        print("\n" + "=" * 76)
        print("     🖐️ BAXTER 3D FINGERTIP SPATIAL TRACKER & SIM-TO-REAL LIVE 🖐️")
        print("=" * 76)
        print(f"  Camera Device:   /dev/video{self.camera_id}")
        print(f"  Isaac Sim Bridge: 127.0.0.1:{self.udp_port}")
        print(f"  Active Arm:      {self.active_arm.upper()}")
        print("  Controls:")
        print("    [Tab] / [Space] : Toggle Active Arm (RIGHT <-> LEFT)")
        print("    [c]             : Recalibrate / Re-center 3D Origin at Current Position")
        print("    [e]             : Toggle Continuous Tracking vs Pinch-to-Engage")
        print("    [q] or [ESC]    : Exit Safely")
        print("=" * 76 + "\n")

        window_name = "Baxter 3D Fingertip Spatial Teleoperation"
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # Mirror horizontally for natural hand-eye coordination
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            # Convert BGR to RGB for MediaPipe
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # Recognize hand and fingertip
            res = self.recognizer.recognize(mp_img)

            is_engaged = False
            tip_px = None

            if res.hand_landmarks and len(res.hand_landmarks) > 0:
                lms = res.hand_landmarks[0]
                coord_3d, is_pinched = self.compute_3d_coordinates(lms, w, h)
                self.current_3d = coord_3d

                # Determine if control is engaged
                if self.continuous_mode or is_pinched:
                    is_engaged = True
                    self.trail_3d.append(coord_3d)

                    # Map to Baxter joints and send Sim-to-Real UDP packet
                    joint_angles = self.map_to_baxter_joints(coord_3d)
                    self.send_sim_to_real_command(joint_angles)

                # Draw Hand Skeleton
                for p1, p2 in HAND_CONNECTIONS:
                    pt1 = (int(lms[p1].x * w), int(lms[p1].y * h))
                    pt2 = (int(lms[p2].x * w), int(lms[p2].y * h))
                    cv2.line(frame, pt1, pt2, (80, 200, 255), 2, cv2.LINE_AA)

                for lm in lms:
                    pt = (int(lm.x * w), int(lm.y * h))
                    cv2.circle(frame, pt, 4, (0, 255, 180), -1, cv2.LINE_AA)

                # Highlight Index Fingertip
                tip_px = (int(lms[8].x * w), int(lms[8].y * h))
                self.trail_2d.append(tip_px)

                # Draw 2D fingertip trail
                for i in range(len(self.trail_2d) - 1):
                    alpha = (i + 1) / len(self.trail_2d)
                    col = (int(255 * alpha), int(200 * alpha), int(50 * alpha))
                    cv2.line(frame, self.trail_2d[i], self.trail_2d[i+1], col, max(1, int(4 * alpha)), cv2.LINE_AA)

                # Glowing 3D Reticle on fingertip
                reticle_color = (0, 255, 0) if is_engaged else (0, 165, 255)
                cv2.circle(frame, tip_px, 12, reticle_color, 2, cv2.LINE_AA)
                cv2.circle(frame, tip_px, 4, (0, 255, 255), -1, cv2.LINE_AA)
                cv2.line(frame, (tip_px[0] - 18, tip_px[1]), (tip_px[0] + 18, tip_px[1]), reticle_color, 1, cv2.LINE_AA)
                cv2.line(frame, (tip_px[0], tip_px[1] - 18), (tip_px[0], tip_px[1] + 18), reticle_color, 1, cv2.LINE_AA)

                # Floating 3D Badge beside fingertip
                badge_text = f"({coord_3d[0]:+.2f}, {-coord_3d[1]:+.2f}, {coord_3d[2]:.2f})m"
                cv2.putText(frame, badge_text, (tip_px[0] + 16, tip_px[1] - 8), cv2.FONT_HERSHEY_DUPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

            else:
                self.current_3d = None
                if len(self.trail_2d) > 0:
                    self.trail_2d.popleft()

            # Status Overlay on Camera View
            status_color = (0, 255, 100) if is_engaged else (0, 180, 255)
            status_text = "[*] SIM-TO-REAL: ENGAGED" if is_engaged else "[o] HOVER (PINCH TO ENGAGE)"
            if self.continuous_mode:
                status_text = "[*] CONTINUOUS 3D TRACKING ACTIVE"

            cv2.rectangle(frame, (0, 0), (w, 42), (20, 24, 30), -1)
            cv2.putText(frame, status_text, (15, 28), cv2.FONT_HERSHEY_DUPLEX, 0.65, status_color, 1, cv2.LINE_AA)
            cv2.putText(frame, f"ARM: {self.active_arm.upper()} [Tab]", (w - 180, 28), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 200, 0), 1, cv2.LINE_AA)

            # Render 3D isometric spatial workspace view
            iso_vis = self.draw_3d_workspace_isometric(width=340, height=h)

            # Combine camera view and 3D isometric view side-by-side
            combined = np.hstack([frame, iso_vis])

            # Frame rate computation
            self.frame_count += 1
            now = time.time()
            if now - self.last_time >= 1.0:
                self.fps = self.frame_count / (now - self.last_time)
                self.frame_count = 0
                self.last_time = now

            cv2.imshow(window_name, combined)

            # Keyboard interactions
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')): # ESC or 'q'
                break
            elif key in (9, ord(' ')): # Tab or Space: Toggle arm
                self.active_arm = "left" if self.active_arm == "right" else "right"
                self.filtered_arm = list(NEUTRAL_ARM[self.active_arm])
                print(f"[*] Switched active control arm to: {self.active_arm.upper()}")
            elif key == ord('c'): # Calibrate origin
                if self.current_3d is not None:
                    self.origin_3d = self.current_3d.copy()
                    print(f"[*] Calibrated 3D origin at: ({self.origin_3d[0]:.3f}, {self.origin_3d[1]:.3f}, {self.origin_3d[2]:.3f})")
            elif key == ord('e'): # Toggle continuous mode
                self.continuous_mode = not self.continuous_mode
                mode_str = "CONTINUOUS (Always Follows)" if self.continuous_mode else "PINCH-TO-ENGAGE"
                print(f"[*] Tracking Mode: {mode_str}")

        cap.release()
        cv2.destroyAllWindows()


def main():
    tracker = Fingertip3DTracker(camera_id=0, udp_port=UDP_PORT)
    tracker.run()


if __name__ == "__main__":
    main()
