#!/usr/bin/env python3
"""
3D Fingertip Spatial Workspace & Full-Perspective Depth Visualizer.
Uses the attached camera to track the user's index fingertip in metric 3D space (X, Y, Z in meters)
and renders a full 3D perspective virtual environment with dynamic depth scaling,
dual-plane orthogonal drop shadows, 3D trajectory ribbons, and real-time Sim-to-Real streaming.
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

# Model asset
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

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # Index
    (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
    (9, 13), (13, 14), (14, 15), (15, 16), # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
    (0, 17)                                # Palm base
]


class Perspective3DTracker:
    def __init__(self, camera_id: int = 0, udp_port: int = UDP_PORT):
        self.camera_id = camera_id
        self.udp_port = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

        # Initialize MediaPipe Hand / Gesture Recognizer
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=1
        )
        self.recognizer = vision.GestureRecognizer.create_from_options(options)

        # 3D Virtual Camera parameters (Orbit Camera)
        self.azimuth_deg = 35.0   # Horizontal rotation around scene
        self.elevation_deg = 22.0 # Vertical pitch angle
        self.camera_dist = 1.35   # Distance to target
        self.fov_deg = 50.0

        # Mouse drag state for interactive 3D orbit
        self.is_dragging = False
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        # Tracking state
        self.active_arm = "right"
        self.continuous_mode = True
        self.origin_3d: Optional[np.ndarray] = None # Calibrated center (X, Y, Z)
        self.current_3d: Optional[np.ndarray] = None
        self.trail_3d = collections.deque(maxlen=45)
        self.trail_2d = collections.deque(maxlen=30)

        # Baxter joint targets
        self.filtered_arm = list(NEUTRAL_ARM[self.active_arm])
        self.alpha = 0.22

        # Sensitivity gains (rad/meter)
        self.gain_x = 1.9
        self.gain_y = 2.2
        self.gain_z = 1.8

        # Performance stats
        self.fps = 0.0
        self.last_time = time.time()
        self.frame_count = 0

    def compute_3d_coordinates(self, landmarks, img_w: int, img_h: int) -> Tuple[np.ndarray, bool]:
        """Computes metric 3D position (X, Y, Z) in meters of index fingertip (landmark 8)."""
        tip = landmarks[8]
        idx_mcp = landmarks[5]
        pky_mcp = landmarks[17]
        thumb_tip = landmarks[4]

        u_tip = tip.x * img_w
        v_tip = tip.y * img_h
        u5, v5 = idx_mcp.x * img_w, idx_mcp.y * img_h
        u17, v17 = pky_mcp.x * img_w, pky_mcp.y * img_h

        # Knuckle pixel span
        knuckle_px = max(12.0, math.hypot(u5 - u17, v5 - v17))

        # Camera horizontal focal length (standard ~60 deg FOV)
        fx = (img_w / 2.0) / math.tan(math.radians(30.0))
        fy = fx

        # Adult human knuckle span: 7.5 cm = 0.075 m
        K_WIDTH_M = 0.075
        z_m = (fx * K_WIDTH_M) / knuckle_px
        z_m = max(0.20, min(1.40, z_m))

        # Optical center projection
        cx, cy = img_w / 2.0, img_h / 2.0
        x_m = ((u_tip - cx) * z_m) / fx
        y_m = ((v_tip - cy) * z_m) / fy

        # Pinch detection (thumb tip to index tip)
        u4, v4 = thumb_tip.x * img_w, thumb_tip.y * img_h
        pinch_dist = math.hypot(u4 - u_tip, v4 - v_tip)
        is_pinched = pinch_dist < (knuckle_px * 0.40)

        coord_3d = np.array([x_m, y_m, z_m], dtype=np.float32)
        return coord_3d, is_pinched

    def map_to_baxter_joints(self, pos_3d: np.ndarray) -> List[float]:
        """Maps relative 3D displacement to 7-DOF Baxter arm joint angles."""
        if self.origin_3d is None:
            self.origin_3d = pos_3d.copy()

        dx = pos_3d[0] - self.origin_3d[0]
        dy = -(pos_3d[1] - self.origin_3d[1])
        dz = -(pos_3d[2] - self.origin_3d[2])

        neutral = NEUTRAL_ARM[self.active_arm]
        target = list(neutral)

        # Shoulder pan (s0)
        target[0] = max(LIMITS['s0'][0], min(LIMITS['s0'][1], neutral[0] + self.gain_x * dx))
        # Shoulder pitch (s1)
        target[1] = max(LIMITS['s1'][0], min(LIMITS['s1'][1], neutral[1] + self.gain_y * dy))
        # Elbow pitch (e1)
        target[3] = max(LIMITS['e1'][0], min(LIMITS['e1'][1], neutral[3] - self.gain_z * dz))

        for i in range(7):
            self.filtered_arm[i] = self.alpha * target[i] + (1.0 - self.alpha) * self.filtered_arm[i]

        return self.filtered_arm

    def send_sim_to_real_command(self, joint_angles: List[float], pos_3d: np.ndarray):
        """Streams joint commands and 3D marker coordinates to Isaac Sim via UDP."""
        try:
            payload = {
                "names": JOINTS[self.active_arm],
                "command": [float(a) for a in joint_angles],
                "marker": [float(pos_3d[0]), float(pos_3d[1]), float(pos_3d[2])]
            }
            self.sock.sendto(json.dumps(payload).encode("utf-8"), (UDP_IP, self.udp_port))
        except Exception:
            pass

    def build_view_proj_matrix(self, width: int, height: int) -> Tuple[np.ndarray, np.ndarray]:
        """Builds 3D perspective View-Projection matrix from orbit spherical camera."""
        az = math.radians(self.azimuth_deg)
        el = math.radians(self.elevation_deg)
        eye = np.array([
            self.camera_dist * math.cos(el) * math.sin(az),
            self.camera_dist * math.sin(el),
            self.camera_dist * math.cos(el) * math.cos(az)
        ], dtype=np.float32)

        target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        forward = target - eye
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, up)
        right /= np.linalg.norm(right)
        true_up = np.cross(right, forward)

        V = np.eye(4, dtype=np.float32)
        V[0, :3] = right
        V[1, :3] = true_up
        V[2, :3] = -forward
        V[:3, 3] = -np.dot(V[:3, :3], eye)

        aspect = width / height
        f = 1.0 / math.tan(math.radians(self.fov_deg) / 2.0)
        P = np.zeros((4, 4), dtype=np.float32)
        P[0, 0] = f / aspect
        P[1, 1] = f
        P[2, 2] = -1.0
        P[2, 3] = -0.1
        P[3, 2] = -1.0

        VP = np.dot(P, V)
        return VP, eye

    def project_3d_point(self, p3d, VP: np.ndarray, width: int, height: int) -> Tuple[Optional[Tuple[int, int]], float]:
        """Projects a 3D point (x, y, z) into 2D screen coordinates with camera depth."""
        p_homo = np.array([p3d[0], p3d[1], p3d[2], 1.0], dtype=np.float32)
        clip = np.dot(VP, p_homo)
        if clip[3] <= 0.001:
            return None, 0.0
        ndc = clip[:3] / clip[3]
        u = int((ndc[0] * 0.5 + 0.5) * width)
        v = int((-ndc[1] * 0.5 + 0.5) * height)
        return (u, v), float(clip[3])

    def render_3d_perspective_scene(self, width: int = 580, height: int = 640) -> np.ndarray:
        """
        Renders a full 3D perspective virtual space with perspective grid,
        dual drop shadows (floor + back wall), dynamic depth sphere scaling, and trajectory ribbons.
        """
        vis = np.zeros((height, width, 3), dtype=np.uint8)
        # Deep space dark gradient background
        for row in range(height):
            ratio = row / height
            vis[row, :] = (int(16 + ratio * 10), int(18 + ratio * 12), int(24 + ratio * 16))

        VP, eye = self.build_view_proj_matrix(width, height)

        # 1. Draw 3D Ground Grid (Floor at Y = -0.28m)
        y_floor = -0.28
        grid_range = 0.35
        step = 0.07

        # Grid lines parallel to X and Z
        for z in np.arange(-grid_range, grid_range + 0.01, step):
            p1, _ = self.project_3d_point([-grid_range, y_floor, z], VP, width, height)
            p2, _ = self.project_3d_point([grid_range, y_floor, z], VP, width, height)
            if p1 and p2:
                col = (55, 65, 80) if abs(z) < 0.01 else (35, 42, 52)
                thickness = 2 if abs(z) < 0.01 else 1
                cv2.line(vis, p1, p2, col, thickness, cv2.LINE_AA)

        for x in np.arange(-grid_range, grid_range + 0.01, step):
            p1, _ = self.project_3d_point([x, y_floor, -grid_range], VP, width, height)
            p2, _ = self.project_3d_point([x, y_floor, grid_range], VP, width, height)
            if p1 and p2:
                col = (55, 65, 80) if abs(x) < 0.01 else (35, 42, 52)
                thickness = 2 if abs(x) < 0.01 else 1
                cv2.line(vis, p1, p2, col, thickness, cv2.LINE_AA)

        # 2. Draw 3D Bounding Workspace Cage (Corner Pillars)
        z_back = -grid_range
        corners = [
            (-grid_range, -grid_range), (grid_range, -grid_range),
            (grid_range, grid_range), (-grid_range, grid_range)
        ]
        y_ceil = 0.28
        for cx, cz in corners:
            p_bot, _ = self.project_3d_point([cx, y_floor, cz], VP, width, height)
            p_top, _ = self.project_3d_point([cx, y_ceil, cz], VP, width, height)
            if p_bot and p_top:
                cv2.line(vis, p_bot, p_top, (40, 50, 65), 1, cv2.LINE_AA)

        # Top ceiling perimeter
        for i in range(4):
            c1, c2 = corners[i], corners[(i + 1) % 4]
            p1, _ = self.project_3d_point([c1[0], y_ceil, c1[1]], VP, width, height)
            p2, _ = self.project_3d_point([c2[0], y_ceil, c2[1]], VP, width, height)
            if p1 and p2:
                cv2.line(vis, p1, p2, (45, 55, 70), 1, cv2.LINE_AA)

        # 3. 3D Coordinate Origin Axes (RGB = XYZ)
        po, _ = self.project_3d_point([0, 0, 0], VP, width, height)
        px, _ = self.project_3d_point([0.15, 0, 0], VP, width, height)
        py, _ = self.project_3d_point([0, 0.15, 0], VP, width, height)
        pz, _ = self.project_3d_point([0, 0, 0.15], VP, width, height)

        if po and px:
            cv2.line(vis, po, px, (0, 0, 230), 2, cv2.LINE_AA)
            cv2.putText(vis, "+X", (px[0] + 4, px[1]), cv2.FONT_HERSHEY_PLAIN, 0.8, (0, 0, 255), 1)
        if po and py:
            cv2.line(vis, po, py, (0, 230, 0), 2, cv2.LINE_AA)
            cv2.putText(vis, "+Y", (py[0], py[1] - 4), cv2.FONT_HERSHEY_PLAIN, 0.8, (0, 255, 0), 1)
        if po and pz:
            cv2.line(vis, po, pz, (230, 160, 0), 2, cv2.LINE_AA)
            cv2.putText(vis, "+Z (Depth)", (pz[0] + 4, pz[1]), cv2.FONT_HERSHEY_PLAIN, 0.8, (255, 180, 0), 1)

        # 4. Draw 3D Trajectory Ribbon (Glowing path in 3D space)
        if self.origin_3d is not None and len(self.trail_3d) > 1:
            projected_trail = []
            for p in self.trail_3d:
                rel = p - self.origin_3d
                # Flip Y and Z to match standard 3D workspace orientation
                p_3d_world = [rel[0], -rel[1], -rel[2]]
                pt_scr, d_cam = self.project_3d_point(p_3d_world, VP, width, height)
                if pt_scr:
                    projected_trail.append((pt_scr, d_cam))

            for i in range(len(projected_trail) - 1):
                (p1, d1), (p2, d2) = projected_trail[i], projected_trail[i + 1]
                fade = (i + 1) / len(projected_trail)
                # Color transitions from deep blue to bright electric cyan
                col_b = int(255 * fade)
                col_g = int(220 * fade)
                col_r = int(50 * fade)
                thick = max(1, int(3.5 * fade))
                cv2.line(vis, p1, p2, (col_b, col_g, col_r), thick, cv2.LINE_AA)

        # 5. Draw Active 3D Fingertip Point with Dynamic Depth Scaling & Shadows
        if self.current_3d is not None and self.origin_3d is not None:
            rel = self.current_3d - self.origin_3d
            p_world = [rel[0], -rel[1], -rel[2]]

            # Project 3D point
            p_scr, d_cam = self.project_3d_point(p_world, VP, width, height)

            # A. Dual Orthogonal Drop Shadows
            # Floor Shadow (Y = y_floor)
            p_floor, d_fl = self.project_3d_point([p_world[0], y_floor, p_world[2]], VP, width, height)
            if p_floor:
                # Floor shadow size scales with height from floor
                h_above_floor = p_world[1] - y_floor
                s_rx = max(4, int(16.0 / (1.0 + h_above_floor * 2.5)))
                s_ry = max(2, int(8.0 / (1.0 + h_above_floor * 2.5)))
                cv2.ellipse(vis, p_floor, (s_rx, s_ry), 0, 0, 360, (20, 24, 30), -1, cv2.LINE_AA)
                cv2.ellipse(vis, p_floor, (s_rx + 2, s_ry + 1), 0, 0, 360, (40, 50, 65), 1, cv2.LINE_AA)

                # Vertical connector line from point to floor shadow (showing height Y)
                if p_scr:
                    cv2.line(vis, p_scr, p_floor, (0, 160, 220), 1, cv2.LINE_AA)

            # Back-Wall Shadow (Z = z_back)
            p_wall, d_wl = self.project_3d_point([p_world[0], p_world[1], z_back], VP, width, height)
            if p_wall:
                dist_to_wall = p_world[2] - z_back
                w_r = max(3, int(14.0 / (1.0 + dist_to_wall * 2.5)))
                cv2.circle(vis, p_wall, w_r, (25, 30, 38), -1, cv2.LINE_AA)
                cv2.circle(vis, p_wall, w_r + 1, (45, 55, 70), 1, cv2.LINE_AA)
                if p_scr:
                    cv2.line(vis, p_scr, p_wall, (30, 60, 80), 1, cv2.LINE_AA)

            # B. The 3D Point (Sphere with Depth Scaling and Radial 3D Lighting)
            if p_scr:
                # Perspective sphere radius scaling with camera depth distance
                base_radius_world = 0.024 # 2.4 cm radius in 3D world
                proj_radius = max(6, int((base_radius_world / d_cam) * (height / math.tan(math.radians(self.fov_deg)/2.0))))

                # Outer glowing halo
                cv2.circle(vis, p_scr, proj_radius + 6, (0, 140, 255), 1, cv2.LINE_AA)
                cv2.circle(vis, p_scr, proj_radius + 3, (0, 200, 255), 1, cv2.LINE_AA)

                # 3D Shaded Sphere (Radial gradient highlight)
                # Base body
                cv2.circle(vis, p_scr, proj_radius, (0, 220, 255), -1, cv2.LINE_AA)
                # Specular top-front highlight
                highlight_center = (p_scr[0] - int(proj_radius * 0.3), p_scr[1] - int(proj_radius * 0.3))
                highlight_r = max(2, int(proj_radius * 0.45))
                cv2.circle(vis, highlight_center, highlight_r, (230, 255, 255), -1, cv2.LINE_AA)

                # Floating 3D Metric Coordinate Tag
                tag = f"({rel[0]:+.2f}, {-rel[1]:+.2f}, {-rel[2]:+.2f})m"
                cv2.putText(vis, tag, (p_scr[0] + proj_radius + 8, p_scr[1] - 4), cv2.FONT_HERSHEY_DUPLEX, 0.42, (0, 255, 255), 1, cv2.LINE_AA)

        # 6. Viewport Title & Camera Orbit Indicators
        cv2.rectangle(vis, (0, 0), (width, 42), (22, 26, 34), -1)
        cv2.putText(vis, "3D PERSPECTIVE SPACE (DEPTH Z)", (12, 18), cv2.FONT_HERSHEY_DUPLEX, 0.48, (0, 230, 255), 1, cv2.LINE_AA)
        orbit_info = f"Orbit: Az={self.azimuth_deg:.0f}d El={self.elevation_deg:.0f}d Dist={self.camera_dist:.2f}m [Click+Drag to Orbit]"
        cv2.putText(vis, orbit_info, (12, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (150, 165, 185), 1)

        # 7. Bottom Metric Telemetry Overlay
        y_bot = height - 90
        cv2.rectangle(vis, (0, y_bot), (width, height), (20, 24, 30), -1)
        cv2.line(vis, (0, y_bot), (width, y_bot), (50, 60, 75), 1)

        if self.current_3d is not None and self.origin_3d is not None:
            rel = self.current_3d - self.origin_3d
            dx_cm = rel[0] * 100.0
            dy_cm = -rel[1] * 100.0
            dz_cm = -rel[2] * 100.0
            abs_z_cm = self.current_3d[2] * 100.0

            line1 = f"3D SPATIAL DISPLACEMENT:  X: {dx_cm:+5.1f} cm  |  Y: {dy_cm:+5.1f} cm  |  Z (DEPTH): {dz_cm:+5.1f} cm"
            line2 = f"CAMERA METRIC DISTANCE :  Z = {abs_z_cm:5.1f} cm from lens   (Moving finger in/out changes depth Z)"
            cv2.putText(vis, line1, (14, y_bot + 24), cv2.FONT_HERSHEY_DUPLEX, 0.46, (0, 255, 220), 1, cv2.LINE_AA)
            cv2.putText(vis, line2, (14, y_bot + 48), cv2.FONT_HERSHEY_DUPLEX, 0.44, (255, 200, 0), 1, cv2.LINE_AA)
        else:
            cv2.putText(vis, "Place index fingertip in front of camera to generate 3D point", (14, y_bot + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (130, 140, 155), 1)

        # Baxter joint angles
        s0_deg = self.filtered_arm[0] * 57.2958
        s1_deg = self.filtered_arm[1] * 57.2958
        e1_deg = self.filtered_arm[3] * 57.2958
        baxter_str = f"Baxter {self.active_arm.upper()}: s0={s0_deg:+5.1f}d | s1={s1_deg:+5.1f}d | e1={e1_deg:+5.1f}d | FPS: {self.fps:4.1f}"
        cv2.putText(vis, baxter_str, (14, y_bot + 72), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 195, 210), 1)

        return vis

    def render_depth_gauge(self, height: int = 640, width: int = 42) -> np.ndarray:
        """Renders an intuitive vertical depth thermometer/gauge in centimeters."""
        gauge = np.zeros((height, width, 3), dtype=np.uint8)
        gauge[:] = (20, 24, 30)

        # Border
        cv2.rectangle(gauge, (4, 40), (width - 4, height - 20), (50, 60, 75), 1)

        # Depth range: 20 cm (near, bottom) to 120 cm (far, top)
        z_min, z_max = 20.0, 120.0

        # Draw tick marks
        for z_val in range(20, 130, 20):
            ratio = 1.0 - (z_val - z_min) / (z_max - z_min)
            y_tick = int(40 + ratio * (height - 60))
            cv2.line(gauge, (width - 12, y_tick), (width - 4, y_tick), (70, 80, 95), 1)

        # Fill depth bar
        if self.current_3d is not None:
            curr_z_cm = self.current_3d[2] * 100.0
            clamped_z = max(z_min, min(z_max, curr_z_cm))
            fill_ratio = 1.0 - (clamped_z - z_min) / (z_max - z_min)
            y_val = int(40 + fill_ratio * (height - 60))

            # Color transitions from green (near) to cyan (mid) to purple (far)
            hue = int(30 + (1.0 - fill_ratio) * 120)
            bgr_col = (0, 220, 255) if fill_ratio > 0.5 else (220, 100, 255)
            cv2.rectangle(gauge, (6, y_val), (width - 6, height - 21), bgr_col, -1)
            cv2.circle(gauge, (width // 2, y_val), 7, (255, 255, 255), -1, cv2.LINE_AA)

        # Title
        cv2.putText(gauge, "Z", (14, 25), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 230, 255), 1)
        return gauge

    def on_mouse(self, event, x, y, flags, param):
        """Interactive mouse callback to orbit/rotate the 3D perspective camera."""
        # Check if click is inside the right 3D viewport (x >= 580)
        viewport_offset_x = 580
        if x >= viewport_offset_x:
            if event == cv2.EVENT_LBUTTONDOWN:
                self.is_dragging = True
                self.last_mouse_x = x
                self.last_mouse_y = y
            elif event == cv2.EVENT_MOUSEMOVE and self.is_dragging:
                dx = x - self.last_mouse_x
                dy = y - self.last_mouse_y
                self.azimuth_deg += dx * 0.5
                self.elevation_deg = max(5.0, min(85.0, self.elevation_deg - dy * 0.4))
                self.last_mouse_x = x
                self.last_mouse_y = y
            elif event == cv2.EVENT_LBUTTONUP:
                self.is_dragging = False

    def run(self):
        """Main real-time tracking and 3D rendering loop."""
        cap = cv2.VideoCapture(self.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap.isOpened():
            print(f"[!] Error: Could not open camera {self.camera_id}")
            return

        print("\n" + "=" * 78)
        print("  🌟 BAXTER 3D FINGERTIP SPATIAL TRACKER & PERSPECTIVE DEPTH VISUALIZER 🌟")
        print("=" * 78)
        print(f"  Camera Device:      /dev/video{self.camera_id}")
        print(f"  Isaac Sim Bridge:    127.0.0.1:{self.udp_port}")
        print(f"  Active Control Arm: {self.active_arm.upper()}")
        print("  Controls:")
        print("    [Click & Drag]   : Orbit / Rotate the 3D perspective space in real time")
        print("    [Left] / [Right] : Rotate 3D camera azimuth")
        print("    [Up] / [Down]    : Rotate 3D camera elevation")
        print("    [+] / [-]        : Zoom camera in / out")
        print("    [Tab] / [Space]  : Toggle Active Arm (RIGHT <-> LEFT)")
        print("    [c]              : Recalibrate / Re-zero 3D Origin at Current Position")
        print("    [e]              : Toggle Continuous Tracking vs Pinch-to-Engage")
        print("    [q] or [ESC]     : Exit Safely")
        print("=" * 78 + "\n")

        window_name = "Baxter 3D Spatial Fingertip & Perspective Depth Tracker"
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(window_name, self.on_mouse)

        cam_view_w = 540
        cam_view_h = 640

        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            h_orig, w_orig = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res = self.recognizer.recognize(mp_img)

            is_engaged = False
            tip_px = None

            if res.hand_landmarks and len(res.hand_landmarks) > 0:
                lms = res.hand_landmarks[0]
                coord_3d, is_pinched = self.compute_3d_coordinates(lms, w_orig, h_orig)
                self.current_3d = coord_3d

                if self.continuous_mode or is_pinched:
                    is_engaged = True
                    self.trail_3d.append(coord_3d)

                    joint_angles = self.map_to_baxter_joints(coord_3d)
                    self.send_sim_to_real_command(joint_angles, coord_3d)

                # Draw Hand Skeleton
                for p1, p2 in HAND_CONNECTIONS:
                    pt1 = (int(lms[p1].x * w_orig), int(lms[p1].y * h_orig))
                    pt2 = (int(lms[p2].x * w_orig), int(lms[p2].y * h_orig))
                    cv2.line(frame, pt1, pt2, (80, 200, 255), 2, cv2.LINE_AA)

                for lm in lms:
                    pt = (int(lm.x * w_orig), int(lm.y * h_orig))
                    cv2.circle(frame, pt, 4, (0, 255, 180), -1, cv2.LINE_AA)

                # Highlight Index Fingertip
                tip_px = (int(lms[8].x * w_orig), int(lms[8].y * h_orig))
                self.trail_2d.append(tip_px)

                for i in range(len(self.trail_2d) - 1):
                    alpha = (i + 1) / len(self.trail_2d)
                    col = (int(255 * alpha), int(200 * alpha), int(50 * alpha))
                    cv2.line(frame, self.trail_2d[i], self.trail_2d[i+1], col, max(1, int(4 * alpha)), cv2.LINE_AA)

                reticle_color = (0, 255, 0) if is_engaged else (0, 165, 255)
                cv2.circle(frame, tip_px, 12, reticle_color, 2, cv2.LINE_AA)
                cv2.circle(frame, tip_px, 4, (0, 255, 255), -1, cv2.LINE_AA)
                cv2.line(frame, (tip_px[0] - 18, tip_px[1]), (tip_px[0] + 18, tip_px[1]), reticle_color, 1, cv2.LINE_AA)
                cv2.line(frame, (tip_px[0], tip_px[1] - 18), (tip_px[0], tip_px[1] + 18), reticle_color, 1, cv2.LINE_AA)

                badge_text = f"Z: {coord_3d[2]*100.0:.0f}cm"
                cv2.putText(frame, badge_text, (tip_px[0] + 16, tip_px[1] - 8), cv2.FONT_HERSHEY_DUPLEX, 0.48, (0, 255, 255), 1, cv2.LINE_AA)

            else:
                self.current_3d = None
                if len(self.trail_2d) > 0:
                    self.trail_2d.popleft()

            # Resize camera view to fit panel
            frame_resized = cv2.resize(frame, (cam_view_w, cam_view_h), interpolation=cv2.INTER_LINEAR)

            # Camera Status Bar
            cv2.rectangle(frame_resized, (0, 0), (cam_view_w, 40), (22, 26, 34), -1)
            status_color = (0, 255, 100) if is_engaged else (0, 180, 255)
            status_text = "[*] CONTINUOUS 3D TRACKING ACTIVE" if self.continuous_mode else ("[*] SIM-TO-REAL: ENGAGED" if is_engaged else "[o] HOVER (PINCH TO ENGAGE)")
            cv2.putText(frame_resized, status_text, (12, 26), cv2.FONT_HERSHEY_DUPLEX, 0.48, status_color, 1, cv2.LINE_AA)

            # Camera bottom instruction bar
            cv2.rectangle(frame_resized, (0, cam_view_h - 45), (cam_view_w, cam_view_h), (20, 24, 30), -1)
            cv2.putText(frame_resized, "Move finger closer/farther to change depth Z in 3D space", (12, cam_view_h - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 195, 210), 1)
            cv2.putText(frame_resized, "Hotkeys: [c]=Re-zero | [Tab]=Arm | [Arrows]=Rotate 3D", (12, cam_view_h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (120, 135, 150), 1)

            # Render 3D Perspective Scene
            persp_scene = self.render_3d_perspective_scene(width=580, height=cam_view_h)

            # Render Vertical Depth Gauge
            gauge = self.render_depth_gauge(height=cam_view_h, width=38)

            # Horizontal Stack: [Camera View] + [Depth Gauge] + [3D Perspective View]
            combined = np.hstack([frame_resized, gauge, persp_scene])

            # FPS
            self.frame_count += 1
            now = time.time()
            if now - self.last_time >= 1.0:
                self.fps = self.frame_count / (now - self.last_time)
                self.frame_count = 0
                self.last_time = now

            cv2.imshow(window_name, combined)

            # Key handling
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                break
            elif key in (9, ord(' ')): # Tab / Space: Switch arm
                self.active_arm = "left" if self.active_arm == "right" else "right"
                self.filtered_arm = list(NEUTRAL_ARM[self.active_arm])
                print(f"[*] Active Control Arm -> {self.active_arm.upper()}")
            elif key == ord('c'): # Calibrate origin
                if self.current_3d is not None:
                    self.origin_3d = self.current_3d.copy()
                    print(f"[*] Calibrated 3D origin at Z={self.origin_3d[2]:.3f}m")
            elif key == ord('e'): # Toggle continuous mode
                self.continuous_mode = not self.continuous_mode
                print(f"[*] Mode: {'CONTINUOUS' if self.continuous_mode else 'PINCH-TO-ENGAGE'}")
            elif key in (ord('a'), 81): # Left arrow
                self.azimuth_deg -= 5.0
            elif key in (ord('d'), 83): # Right arrow
                self.azimuth_deg += 5.0
            elif key in (ord('w'), 82): # Up arrow
                self.elevation_deg = min(85.0, self.elevation_deg + 4.0)
            elif key in (ord('s'), 84): # Down arrow
                self.elevation_deg = max(5.0, self.elevation_deg - 4.0)
            elif key in (ord('+'), ord('=')): # Zoom in
                self.camera_dist = max(0.6, self.camera_dist - 0.1)
            elif key in (ord('-'), ord('_')): # Zoom out
                self.camera_dist = min(3.0, self.camera_dist + 0.1)

        cap.release()
        cv2.destroyAllWindows()


Fingertip3DTracker = Perspective3DTracker


def main():
    tracker = Perspective3DTracker(camera_id=0, udp_port=UDP_PORT)
    tracker.run()


if __name__ == "__main__":
    main()
