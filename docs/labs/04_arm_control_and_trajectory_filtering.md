# Lab 4: Arm Control, Joint Jogging & Trajectory Filtering

*Controlling 7-DOF limbs, low-pass trajectory interpolation, dampening SEA oscillations, and jogging joints.*

---

## 1. Objectives

By the end of this lab, you will:
1. Master joint-level control of Baxter's 7-DOF articulating arms.
2. Understand why step commands cause mechanical resonance in Series Elastic Actuators (SEAs).
3. Implement a continuous first-order low-pass filter and quintic polynomial trajectory generator.
4. Jog individual joints using the `baxter jog` CLI tool.
5. Program custom multi-joint poses and choreographies (`wave`, `cheer`, `salute`) using the Python API.

---

## 2. Series Elastic Actuators (SEA) & The Resonance Trap

Traditional industrial robotic arms (like KUKA or FANUC) have rigid harmonic drives and stiff steel shafts. You can command them with instantaneous step inputs, and the arm will snap to position aggressively.

Baxter is fundamentally different: **every joint has a calibrated torsional spring between the motor and the limb**.

```text
  [Motor + Gearbox] ─── (Torsion Spring: Ks) ─── [Output Link / Arm]
```

### The Spring Resonance Phenomenon:
If you publish a sudden step change in target position:
1. The motor accelerates rapidly, winding up the torsion spring.
2. The spring releases stored energy, overshooting the target.
3. The limb violently oscillates back and forth at the mechanical natural frequency ($\approx 2 \dots 5\text{ Hz}$), causing Baxter to shudder and trip an amplifier torque safety error!

### The Mathematical Solution: Trajectory Filtering
All commanded trajectories must be smoothly interpolated. `baxter-py` employs a digital first-order low-pass filter and minimum-jerk (quintic polynomial) interpolation:

$$q_k = q_{k-1} + \alpha \cdot (q_{\text{target}} - q_{k-1})$$

Where $\alpha \in (0, 1]$ is the smoothing factor calibrated to Baxter's internal SEA time constants ($\tau \approx 0.1\text{ s}$).

---

## 3. Joint Jogging via the CLI

You can jog individual joints by specified angle offsets (in degrees) directly from your terminal:

```bash
# Syntax: baxter jog <arm: left|right> <joint_name> <delta_deg>

# Rotate Right Shoulder Pan outward by 10 degrees
baxter jog right s0 10.0

# Rotate Right Shoulder Pan inward by 10 degrees
baxter jog right s0 -10.0

# Flex Left Elbow forward by 15 degrees
baxter jog left e1 15.0

# Rotate Right Forearm (Wrist Roll w0) by 20 degrees
baxter jog right w0 20.0
```

*Joint Names*: `s0` (Shoulder Pan), `s1` (Shoulder Pitch), `e0` (Elbow Roll), `e1` (Elbow Pitch), `w0` (Wrist Roll), `w1` (Wrist Pitch), `w2` (Wrist Roll 2).

---

## 4. Built-In Choreography Routines

`baxter-py` includes calibrated multi-joint posture presets:

```bash
# Friendly welcoming wave gesture
baxter move wave

# Dual-arm celebratory victory cheer
baxter move cheer

# Military-style smart salute
baxter move salute

# Forward reaching grasping stance
baxter move reach

# Return to symmetrical operational neutral
baxter move neutral
```

---

## 5. Python API: Multi-Joint Trajectory Interpolation

Here is how to create a custom smooth multi-waypoint motion generator using `baxter-py`:

```python
#!/usr/bin/env python3
"""Lab 4: Custom Smooth Arm Motion Generator."""
import asyncio
import math
from baxter import Baxter

async def move_to_pose(robot, arm_name, target_joints, duration=2.5, steps=50):
    """Interpolates joints smoothly using minimum-jerk cosine ramping."""
    current_joints = await robot.get_joint_positions()
    arm_joints = [j for j in current_joints if j.startswith(arm_name)]
    
    start_angles = {j: current_joints[j] for j in arm_joints}
    dt = duration / steps
    
    for i in range(steps + 1):
        # Cosine s-curve profile (0.0 to 1.0)
        t = i / steps
        alpha = 0.5 * (1.0 - math.cos(math.pi * t))
        
        step_command = {}
        for j, target_val in target_joints.items():
            start_val = start_angles.get(j, 0.0)
            step_command[j] = start_val + alpha * (target_val - start_val)
            
        await robot.send_joint_command(arm_name, step_command)
        await asyncio.sleep(dt)

async def main():
    async with Baxter() as robot:
        state = await robot.get_state()
        if not state.get("enabled"):
            await robot.enable()

        print("Executing custom waving choreography...")
        
        # High wave pose
        wave_high = {
            "right_s0": -0.20,
            "right_s1": -0.80,
            "right_e0": 1.20,
            "right_e1": 1.70,
            "right_w0": 0.0,
            "right_w1": -0.60,
            "right_w2": 0.0,
        }
        
        # Wave left pose
        wave_tilt = {
            "right_s0": -0.20,
            "right_s1": -0.80,
            "right_e0": 1.20,
            "right_e1": 1.70,
            "right_w0": 0.0,
            "right_w1": 0.20,
            "right_w2": 0.0,
        }
        
        await move_to_pose(robot, "right", wave_high, duration=2.0)
        
        # Oscillate wrist for 3 cycles
        for _ in range(3):
            await move_to_pose(robot, "right", wave_tilt, duration=0.6)
            await move_to_pose(robot, "right", wave_high, duration=0.6)
            
        # Return to neutral
        await robot.untuck(duration=2.5)
        print("Motion complete!")

if __name__ == "__main__":
    asyncio.run(main())
```

In **Lab 5**, we will turn our attention to Baxter's head: rendering emotional facial expressions on the 1024x600 screen and actuating head pan and nod.
