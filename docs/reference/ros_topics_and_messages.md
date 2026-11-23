# Baxter ROS Topics, Services & Messages Reference

*Archived and validated reference of the complete ROS / Rosbridge API on the Rethink Robotics Baxter Research Robot.*

---

## 1. Top-Level Robot State & Power Management

### Topics

| Topic | Message Type | Direction | Description |
| :--- | :--- | :---: | :--- |
| `/robot/state` | `baxter_core_msgs/AssemblyState` | Publish | Current top-level system health, e-stop state, error flags, and motor readiness |
| `/robot/set_super_reset` | `std_msgs/Empty` | Subscribe | Send pulse to clear latched hardware faults and reset controllers |
| `/robot/set_super_enable` | `std_msgs/Bool` | Subscribe | Send `data: True` to energize 48V motor bus relays; `data: False` to disable |
| `/robot/set_super_stop` | `std_msgs/Empty` | Subscribe | Send pulse to assert a software emergency stop |

### `baxter_core_msgs/AssemblyState` Message Definition
```text
bool enabled             # True if 48V power bus is closed and motors energized
bool stopped             # True if an E-Stop condition is asserted
bool error               # True if any hardware component has an active error
uint8 estop_button       # E-Stop button status:
                         #   0 = ESTOP_BUTTON_UNPRESSED (Normal / Released)
                         #   1 = ESTOP_BUTTON_PRESSED (E-Stop Active)
                         #   2 = ESTOP_BUTTON_UNKNOWN
                         #   3 = ESTOP_BUTTON_RELEASED (Released but not reset)
uint8 estop_source       # Source of E-Stop:
                         #   0 = ESTOP_SOURCE_NONE
                         #   1 = ESTOP_SOURCE_USER (Hardware switch)
                         #   2 = ESTOP_SOURCE_UNKNOWN
                         #   3 = ESTOP_SOURCE_FAULT (Joint torque / limit error)
                         #   4 = ESTOP_SOURCE_BRAIN (Watchdog timeout / heartbeat)
bool ready               # True when robot is powered and ready to accept trajectories
```

---

## 2. Arm Joints & Motion Control

### Topics

| Topic | Message Type | Direction | Description |
| :--- | :--- | :---: | :--- |
| `/robot/joint_states` | `sensor_msgs/JointState` | Publish | Real-time positions (rad), velocities (rad/s), and efforts (N·m) for all 15 joints (100 Hz) |
| `/robot/limb/left/joint_command` | `baxter_core_msgs/JointCommand` | Subscribe | Direct joint position, velocity, or torque command stream to left arm |
| `/robot/limb/right/joint_command`| `baxter_core_msgs/JointCommand` | Subscribe | Direct joint position, velocity, or torque command stream to right arm |
| `/robot/limb/left/endpoint_state`| `baxter_core_msgs/EndpointState` | Publish | Cartesian pose $(x, y, z, q_x, q_y, q_z, q_w)$ and wrench (force/torque) of left wrist |
| `/robot/limb/right/endpoint_state`| `baxter_core_msgs/EndpointState`| Publish | Cartesian pose and wrench of right wrist |
| `/robot/limb/left/suppress_collision_avoidance` | `std_msgs/Empty` | Subscribe | Heartbeat pulse (min 5 Hz) to temporarily override internal self-collision modeling |
| `/robot/limb/right/suppress_collision_avoidance`| `std_msgs/Empty` | Subscribe | Heartbeat pulse (min 5 Hz) to temporarily override internal self-collision modeling |

### `baxter_core_msgs/JointCommand` Message Definition
```text
int32 mode               # 1 = POSITION_MODE
                         # 2 = VELOCITY_MODE
                         # 3 = TORQUE_MODE
                         # 4 = RAW_POSITION_MODE
string[] names           # Joint names (e.g. ['right_s0', 'right_s1', 'right_e0', ...])
float64[] command        # Target positions (rad), velocities (rad/s), or torques (N·m)
```

---

## 3. Head & Gaze Interaction

### Topics

| Topic | Message Type | Direction | Description |
| :--- | :--- | :---: | :--- |
| `/robot/head/head_state` | `baxter_core_msgs/HeadState` | Publish | Current head pan angle, is_turning, and is_nodding flags |
| `/robot/head/command_head_pan` | `baxter_core_msgs/HeadPanCommand` | Subscribe | Target pan angle in radians `[-1.571, +1.571]` and target speed `[0, 100]` |
| `/robot/head/command_head_nod` | `std_msgs/Bool` | Subscribe | Send `True` to trigger affirmative head nod cycle |

---

## 4. Head Display (xdisplay)

### Topics

| Topic | Message Type | Direction | Description |
| :--- | :--- | :---: | :--- |
| `/robot/xdisplay` | `sensor_msgs/Image` | Subscribe | Raw RGB8 / BGR8 image stream to display on 1024x600 head LCD screen |

---

## 5. Cameras

### Topics

| Topic | Message Type | Direction | Description |
| :--- | :--- | :---: | :--- |
| `/cameras/head_camera/image` | `sensor_msgs/Image` | Publish | Head camera image stream |
| `/cameras/left_hand_camera/image` | `sensor_msgs/Image` | Publish | Left wrist camera image stream |
| `/cameras/right_hand_camera/image`| `sensor_msgs/Image` | Publish | Right wrist camera image stream |
| `/cameras/head_camera/camera_info` | `sensor_msgs/CameraInfo` | Publish | Calibration matrix, distortion parameters, and focal lengths |

### Services

| Service | Service Type | Description |
| :--- | :--- | :--- |
| `/cameras/open` | `baxter_core_msgs/OpenCamera` | Open a camera with specified width, height, and framerate |
| `/cameras/close` | `baxter_core_msgs/CloseCamera` | Close a camera to free USB bandwidth |
| `/cameras/list` | `baxter_core_msgs/ListCameras` | Enumerate available physical cameras |

---

## 6. End-Effectors (Grippers) & Cuff Inputs

### Topics

| Topic | Message Type | Direction | Description |
| :--- | :--- | :---: | :--- |
| `/robot/end_effector/left_gripper/state` | `baxter_core_msgs/EndEffectorState` | Publish | Position, gripping state, force, error |
| `/robot/end_effector/left_gripper/command` | `baxter_core_msgs/EndEffectorCommand` | Subscribe | Position command `[0.0, 100.0]` or Grip / Release commands |
| `/robot/digital_io/left_lower_cuff_button/state` | `baxter_core_msgs/DigitalIOState` | Publish | State of lower rubber cuff squeeze sensor (Zero-G toggle) |
| `/robot/digital_io/left_upper_button/state` | `baxter_core_msgs/DigitalIOState` | Publish | State of upper circular button on cuff |
