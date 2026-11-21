#!/usr/bin/env python3
"""
Baxter Interactive Control HUD (Heads-Up Display)
Floating graphical teleoperation panel running alongside NVIDIA Isaac Sim.
Sends zero-latency commands to the Isaac Sim Sim-to-Real bridge via UDP port 19888.
"""

import os
import sys
import json
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk

UDP_PORT = 19888
UDP_IP = "127.0.0.1"

class BaxterHUD:
    def __init__(self, root):
        self.root = root
        self.root.title("Baxter Sim-to-Real Control HUD")
        self.root.geometry("380x880+1520+70")
        self.root.configure(bg="#16181d")
        self.root.attributes("-topmost", True)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.active_arm = "RIGHT"
        self.s2r_enabled = True

        self.build_ui()
        self.bind_keys()

    def send_cmd(self, payload: dict):
        try:
            raw = json.dumps(payload).encode("utf-8")
            self.sock.sendto(raw, (UDP_IP, UDP_PORT))
        except Exception as e:
            self.lbl_status.config(text=f"Error: {e}", fg="#ff5555")

    def trigger_pose(self, name: str):
        self.send_cmd({"pose": name})
        self.lbl_status.config(text=f"Action: Pose -> {name.upper()}", fg="#00ffcc")

    def trigger_key(self, key_char: str, desc: str):
        self.send_cmd({"key": key_char})
        self.lbl_status.config(text=f"Action: {desc}", fg="#00ffcc")

    def toggle_arm(self):
        self.trigger_key("\t", "Toggled Active Arm")
        self.active_arm = "LEFT" if self.active_arm == "RIGHT" else "RIGHT"
        self.btn_arm.config(text=f"Active Arm: {self.active_arm}")

    def toggle_s2r(self):
        self.trigger_key("m", "Toggled Sim-to-Real")
        self.s2r_enabled = not self.s2r_enabled
        status_text = "Sim-to-Real: ON (Mirrored)" if self.s2r_enabled else "Sim-to-Real: OFF (Sim Only)"
        btn_color = "#00aa66" if self.s2r_enabled else "#aa4400"
        self.btn_s2r.config(text=status_text, bg=btn_color)

    def play_full_show(self):
        def _runner():
            self.lbl_status.config(text="Running Synchronized Show...", fg="#ffff00")
            for p in ["wave", "boxing", "cheer", "neutral"]:
                self.trigger_pose(p)
                time.sleep(3.5)
            self.lbl_status.config(text="Synchronized Show Complete!", fg="#00ffcc")
        threading.Thread(target=_runner, daemon=True).start()

    def build_ui(self):
        # Header
        frame_head = tk.Frame(self.root, bg="#1e222b", pady=10)
        frame_head.pack(fill="x")
        tk.Label(frame_head, text="🤖 BAXTER SIM-TO-REAL", font=("DejaVu Sans", 13, "bold"), fg="#00e5ff", bg="#1e222b").pack()
        tk.Label(frame_head, text="Isaac Sim ⟷ Physical Robot Lockstep", font=("DejaVu Sans", 8), fg="#9aa5b5", bg="#1e222b").pack()

        # Status Label
        self.lbl_status = tk.Label(self.root, text="Ready | Real: Connected", font=("DejaVu Sans", 9, "bold"), fg="#00ffaa", bg="#16181d", pady=8)
        self.lbl_status.pack(fill="x")

        # Preset Poses Section
        lbl_sec1 = tk.Label(self.root, text="PRESET GESTURES & POSES", font=("DejaVu Sans", 9, "bold"), fg="#ffaa00", bg="#16181d", anchor="w", padx=15, pady=4)
        lbl_sec1.pack(fill="x")

        poses = [
            ("👋 Wave Gesture [2]", "wave", "#263238"),
            ("🥊 Boxing Guard [3]", "boxing", "#372727"),
            ("🙌 Victory Cheer [4]", "cheer", "#253325"),
            ("🎯 Operational Neutral [1]", "neutral", "#2a2d34"),
            ("👉 Reach Forward [5]", "reach", "#2a2d34"),
            ("📦 Compact Storage [0]", "tuck", "#202025"),
        ]

        for text, pose, col in poses:
            btn = tk.Button(
                self.root, text=text, font=("DejaVu Sans", 9, "bold"),
                bg=col, fg="#ffffff", activebackground="#00adb5", activeforeground="#ffffff",
                relief="flat", pady=6, cursor="hand2",
                command=lambda p=pose: self.trigger_pose(p)
            )
            btn.pack(fill="x", padx=15, pady=2)

        # Separator
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=15, pady=8)

        # Active Arm & Jogging Section
        lbl_sec2 = tk.Label(self.root, text="DIRECT TELEOPERATION & JOGGING", font=("DejaVu Sans", 9, "bold"), fg="#00e5ff", bg="#16181d", anchor="w", padx=15)
        lbl_sec2.pack(fill="x")

        self.btn_arm = tk.Button(
            self.root, text=f"Active Arm: {self.active_arm} [Tab/Space]", font=("DejaVu Sans", 9, "bold"),
            bg="#303f9f", fg="#ffffff", relief="flat", pady=5, cursor="hand2",
            command=self.toggle_arm
        )
        self.btn_arm.pack(fill="x", padx=15, pady=4)

        # D-pad jog controls
        frame_jog = tk.Frame(self.root, bg="#16181d")
        frame_jog.pack(fill="x", padx=15, pady=4)

        btn_up = tk.Button(frame_jog, text="▲ Shoulder UP [W]", font=("DejaVu Sans", 8, "bold"), bg="#37474f", fg="#fff", relief="flat", pady=4, command=lambda: self.trigger_key("W", "Arm UP (Pitch)"))
        btn_up.pack(fill="x", pady=1)

        frame_lr = tk.Frame(frame_jog, bg="#16181d")
        frame_lr.pack(fill="x", pady=1)
        btn_l = tk.Button(frame_lr, text="◀ Pan OUT [A]", font=("DejaVu Sans", 8, "bold"), bg="#37474f", fg="#fff", relief="flat", width=18, pady=4, command=lambda: self.trigger_key("A", "Arm OUTWARD (Pan)"))
        btn_l.pack(side="left", expand=True, fill="x", padx=(0, 2))
        btn_r = tk.Button(frame_lr, text="Pan IN [D] ▶", font=("DejaVu Sans", 8, "bold"), bg="#37474f", fg="#fff", relief="flat", width=18, pady=4, command=lambda: self.trigger_key("D", "Arm INWARD (Pan)"))
        btn_r.pack(side="right", expand=True, fill="x", padx=(2, 0))

        btn_dn = tk.Button(frame_jog, text="▼ Shoulder DOWN [S]", font=("DejaVu Sans", 8, "bold"), bg="#37474f", fg="#fff", relief="flat", pady=4, command=lambda: self.trigger_key("s", "Arm DOWN (Pitch)"))
        btn_dn.pack(fill="x", pady=1)

        # Elbow controls
        frame_elbow = tk.Frame(frame_jog, bg="#16181d")
        frame_elbow.pack(fill="x", pady=2)
        btn_eflex = tk.Button(frame_elbow, text="Elbow FLEX [R]", font=("DejaVu Sans", 8, "bold"), bg="#263238", fg="#fff", relief="flat", width=18, pady=4, command=lambda: self.trigger_key("R", "Elbow FLEX"))
        btn_eflex.pack(side="left", expand=True, fill="x", padx=(0, 2))
        btn_eext = tk.Button(frame_elbow, text="Elbow EXTEND [F]", font=("DejaVu Sans", 8, "bold"), bg="#263238", fg="#fff", relief="flat", width=18, pady=4, command=lambda: self.trigger_key("f", "Elbow EXTEND"))
        btn_eext.pack(side="right", expand=True, fill="x", padx=(2, 0))

        # Head Pan Controls
        frame_head_ctrl = tk.Frame(self.root, bg="#16181d")
        frame_head_ctrl.pack(fill="x", padx=15, pady=4)
        tk.Button(frame_head_ctrl, text="Head ◀ [[]", font=("DejaVu Sans", 8), bg="#263238", fg="#fff", relief="flat", width=11, pady=3, command=lambda: self.trigger_key("[", "Head PAN LEFT")).pack(side="left", padx=1)
        tk.Button(frame_head_ctrl, text="Center [c]", font=("DejaVu Sans", 8), bg="#263238", fg="#fff", relief="flat", width=11, pady=3, command=lambda: self.trigger_key("c", "Head CENTER")).pack(side="left", padx=1)
        tk.Button(frame_head_ctrl, text="Head ▶ []]", font=("DejaVu Sans", 8), bg="#263238", fg="#fff", relief="flat", width=11, pady=3, command=lambda: self.trigger_key("]", "Head PAN RIGHT")).pack(side="left", padx=1)

        # Separator
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=15, pady=8)

        # Automation & Sync Mode
        self.btn_s2r = tk.Button(
            self.root, text="Sim-to-Real: ON (Mirrored) [m]", font=("DejaVu Sans", 9, "bold"),
            bg="#00aa66", fg="#ffffff", relief="flat", pady=6, cursor="hand2",
            command=self.toggle_s2r
        )
        self.btn_s2r.pack(fill="x", padx=15, pady=3)

        btn_show = tk.Button(
            self.root, text="✨ Play Synchronized Show ✨", font=("DejaVu Sans", 9, "bold"),
            bg="#6a1b9a", fg="#ffffff", relief="flat", pady=6, cursor="hand2",
            command=self.play_full_show
        )
        btn_show.pack(fill="x", padx=15, pady=3)

        # Footer instructions
        tk.Label(
            self.root,
            text="Tip: Click any button or press hotkeys [1-5, WASD] to move Baxter in Isaac Sim & physical robot.",
            font=("DejaVu Sans", 7), fg="#78909c", bg="#16181d", wraplength=340, justify="center", pady=6
        ).pack(side="bottom")

    def bind_keys(self):
        def on_key(event):
            ch = event.char
            keysym = event.keysym
            if ch in ('1', '2', '3', '4', '5', '0'):
                self.trigger_key(ch, f"Pose key [{ch}]")
            elif ch in ('w', 'W'):
                self.trigger_key("W", "Arm UP (Pitch)")
            elif ch in ('s', 'S'):
                self.trigger_key("s", "Arm DOWN (Pitch)")
            elif ch in ('a', 'A'):
                self.trigger_key("A", "Arm OUTWARD (Pan)")
            elif ch in ('d', 'D'):
                self.trigger_key("D", "Arm INWARD (Pan)")
            elif ch in ('r', 'R'):
                self.trigger_key("R", "Elbow FLEX")
            elif ch in ('f', 'F'):
                self.trigger_key("f", "Elbow EXTEND")
            elif ch in ('[', ']', 'c'):
                self.trigger_key(ch, f"Head key [{ch}]")
            elif ch == 'm':
                self.toggle_s2r()
            elif keysym in ('Tab', 'space'):
                self.toggle_arm()

        self.root.bind("<Key>", on_key)

def main():
    root = tk.Tk()
    app = BaxterHUD(root)
    root.mainloop()

if __name__ == "__main__":
    main()
