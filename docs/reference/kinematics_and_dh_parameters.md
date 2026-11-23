# Baxter Kinematics & Denavit-Hartenberg (DH) Parameters

*Archived kinematic reference and analytical model for Baxter's 7-DOF articulating limbs.*

---

## 1. Kinematic Structure

Baxter's arms each consist of 7 revolute joints (7-DOF), arranged in an alternating roll-pitch-roll-pitch-roll-pitch-roll sequence. This kinematics redundancy (7 DOF in 6D Cartesian task space) provides an infinite number of nullspace arm configurations for any valid end-effector pose, enabling obstacle avoidance and natural postures.

```text
 Base Frame (Torso)
      └── Mount (s0 - Shoulder Yaw / Pan)
            └── s1 - Shoulder Pitch
                  └── e0 - Upper Arm Roll / Twist
                        └── e1 - Elbow Pitch
                              └── w0 - Forearm Roll / Twist
                                    └── w1 - Wrist Pitch
                                          └── w2 - Tool Plate Roll
```

---

## 2. Standard Modified DH Parameters (Craig Convention)

The reference frame originates at the torso `base` coordinate frame ($Z$ pointing upward, $X$ pointing forward out of the chest, $Y$ pointing to Baxter's left).

### Left Arm Kinematic Chain:
Mount offset from `base`:
- $X = 0.064\text{ m}$
- $Y = 0.259\text{ m}$
- $Z = 0.120\text{ m}$
- Roll = $-45^\circ$ ($-0.7854\text{ rad}$), Pitch = $0^\circ$, Yaw = $0^\circ$

### Right Arm Kinematic Chain:
Mount offset from `base`:
- $X = 0.064\text{ m}$
- $Y = -0.259\text{ m}$
- $Z = 0.120\text{ m}$
- Roll = $+45^\circ$ ($+0.7854\text{ rad}$), Pitch = $0^\circ$, Yaw = $0^\circ$

### Denavit-Hartenberg (DH) Parameter Table (Relative to Limb Mount)

| Joint $i$ | Joint Name | $\alpha_{i-1}$ | $a_{i-1}$ (m) | $d_i$ (m) | $\theta_i$ (Offset) | Joint Range (rad) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | `s0` | $0$ | $0$ | $0.27035$ | $\theta_1$ | `[-1.701, +1.701]` |
| **2** | `s1` | $-\pi/2$ | $0.069$ | $0$ | $\theta_2 - \pi/2$ | `[-2.147, +1.047]` |
| **3** | `e0` | $+\pi/2$ | $0$ | $0.36435$ | $\theta_3$ | `[-3.054, +3.054]` |
| **4** | `e1` | $-\pi/2$ | $0.069$ | $0$ | $\theta_4$ | `[-0.050, +2.618]` |
| **5** | `w0` | $+\pi/2$ | $0$ | $0.37429$ | $\theta_5$ | `[-3.059, +3.059]` |
| **6** | `w1` | $-\pi/2$ | $0.010$ | $0$ | $\theta_6$ | `[-1.571, +2.094]` |
| **7** | `w2` | $+\pi/2$ | $0$ | $0.229525$| $\theta_7$ | `[-3.059, +3.059]` |

---

## 3. Homogeneous Transformation Matrix

The homogeneous transformation from link $i-1$ to link $i$ using modified DH convention is defined as:

$$^{i-1}T_i = \begin{bmatrix}
\cos\theta_i & -\sin\theta_i & 0 & a_{i-1} \\
\sin\theta_i\cos\alpha_{i-1} & \cos\theta_i\cos\alpha_{i-1} & -\sin\alpha_{i-1} & -d_i\sin\alpha_{i-1} \\
\sin\theta_i\sin\alpha_{i-1} & \cos\theta_i\sin\alpha_{i-1} & \cos\alpha_{i-1} & d_i\cos\alpha_{i-1} \\
0 & 0 & 0 & 1
\end{bmatrix}$$

Multiplying the consecutive transformations gives the full Forward Kinematics (FK) transformation from torso base to the end-effector:

$$^0T_7 = \, ^0T_{\text{mount}} \cdot \, ^1T_2 \cdot \, ^2T_3 \cdot \, ^3T_4 \cdot \, ^4T_5 \cdot \, ^5T_6 \cdot \, ^6T_7$$

---

## 4. Series Elastic Actuators (SEA) Compliance

Unlike rigid industrial arms (which measure motor position directly with high-ratio gearboxes), each Baxter joint contains a calibrated planar steel torsion spring positioned between the gearbox and the output link.

- **Deflection Equation**: $\tau = K_s \cdot (\theta_{\text{output}} - \theta_{\text{motor}})$
- **Spring Constants ($K_s$)**:
  - Shoulder / Elbow (`s0, s1, e0, e1`): ~ $800\text{ N}\cdot\text{m/rad}$
  - Wrist (`w0, w1, w2`): ~ $150\text{ N}\cdot\text{m/rad}$
- **Implication for Control**: Baxter can measure joint torques directly without expensive external force/torque load cells. However, improper trajectory commanding (sudden steps) will excite the spring resonance, resulting in arm oscillations. Trajectories must always be low-pass filtered.
