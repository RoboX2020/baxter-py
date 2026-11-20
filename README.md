# baxter-py

A modern, standalone Python library and unified Command Line Interface (CLI) for the **Rethink Robotics Baxter** research robot.

`baxter-py` communicates natively via high-speed Rosbridge WebSockets (`ws://<ip>:9090`), removing the need for legacy ROS1 workstation installs, Python 2 environments, or catkin workspaces. It runs seamlessly on modern Python 3.10+ environments (including Ubuntu 24.04 and ARM64 / aarch64 architectures).

---

## Features

- **ROS-Agnostic WebSockets Client**: Direct asynchronous communication with Baxter's onboard Rosbridge server.
- **Unified Command Line Tool (`baxter`)**: Complete terminal tool to inspect status, enable/disable motors, jog joints, control display graphics, and trigger choreographies.
- **7-DOF Limb Motion & Filtering**: Smooth first-order low-pass trajectory execution with automated collision avoidance suppression.
- **Vector Screen Display & Facial Expressions**: Real-time 1024x600 LCD rendering with built-in emotional facial expressions (neutral, happy, focused, wink, boxing, disco, surprised, sleepy) and custom banners.
- **Camera Streaming & Vision**: Built-in decoder for head and hand camera streams with support for OpenCV and NumPy.
- **MediaPipe AI Boxing Partner**: Interactive computer vision sparring partner responding in real-time to human jabs, blocks, and hand gestures.
- **High-Level Choreography Engine**: Includes a 5-act orchestral symphony and a 124 BPM musical dance routine.

---

## Installation

Clone the repository and install the package in editable mode:

```bash
git clone https://github.com/RoboX2020/baxter-py.git
cd baxter-py
pip install -e .
```

To include interactive MediaPipe computer vision capabilities:

```bash
pip install -e ".[vision]"
```

---

## Command Line Interface (`baxter`)

Once installed, the `baxter` command is available in your shell:

### 1. State & Power Management
```bash
# Display system health, e-stop state, and all joint positions
baxter status

# Clear fault states and power on arm motors
baxter enable

# Power down arm motors
baxter disable

# Clear fault flags
baxter reset
```

### 2. Arm Motion & Poses
```bash
# Move arms to symmetrical operational neutral posture
baxter untuck

# Safely fold arms into compact shipping/storage pose
baxter tuck

# Execute predefined motion routines
baxter move wave
baxter move cheer
baxter move salute
baxter move reach
baxter move neutral

# Jog individual joints by degrees
# Syntax: baxter jog <left|right> <joint_name> <delta_deg>
baxter jog right s0 10.0
baxter jog left e1 -15.0
```

### 3. Screen Face & Graphics
```bash
# Change facial expression on Baxter's 1024x600 head screen
baxter face happy
baxter face boxing
baxter face disco
baxter face wink
baxter face focused

# Custom banner text
baxter face happy --text "READY FOR EXPERIMENT 1"

# Display custom image from disk
baxter face --image ./path/to/image.png
```

### 4. Head Pan & Nod
```bash
# Pan head (specify angle in degrees with --deg)
baxter head pan 30.0 --deg

# Perform head nod
baxter head nod
```

### 5. Cameras & Vision
```bash
# Capture a snapshot from the head camera to disk
baxter camera snapshot -o head_cam.jpg

# Open live OpenCV preview of the camera stream
baxter camera view
```

### 6. Interactive Vision & Choreography
```bash
# Launch interactive MediaPipe boxing AI sparring session
baxter box --duration 60

# Run Daft Punk style 124 BPM musical dance party
baxter dance

# Run 5-act classical orchestral symphony choreography
baxter symphony
```

---

## Python API Usage

### Quickstart Example

```python
import asyncio
from baxter import Baxter

async def main():
    async with Baxter() as robot:
        # Check motor status and enable if needed
        state = await robot.get_state()
        if not state.get("enabled"):
            await robot.enable()

        # Untuck and display greeting face
        await robot.untuck(duration=3.5)
        await robot.display.show_emotion("happy", status_text="HELLO HUMAN!")

        # Perform friendly wave
        await robot.wave(cycles=3)

        # Jog single joint
        await robot.right_arm.jog("s0", delta_deg=10.0)

        # Return to neutral
        await robot.untuck(duration=3.0)

asyncio.run(main())
```

### Camera & MediaPipe Detection

```python
import asyncio
from baxter import Baxter
from baxter.vision import GestureDetector

async def stream_and_detect():
    detector = GestureDetector()
    async with Baxter() as robot:
        async for frame in robot.camera.stream("head_camera"):
            results = detector.detect(frame)
            for res in results:
                print(f"Hand gesture: {res['gesture']} (score: {res['score']:.2f})")

asyncio.run(stream_and_detect())
```

---

## Directory Structure

```text
baxter-py/
├── baxter/
│   ├── __init__.py      # Package export and version info
│   ├── client.py        # Core Baxter connection and coordinated control
│   ├── limb.py          # Arm control, trajectory interpolation, and jogging
│   ├── head.py          # Head pan, nod, and gaze tracking
│   ├── display.py       # 1024x600 LCD renderer and vector emotions
│   ├── camera.py        # Camera subscriber and frame decoder
│   ├── poses.py         # Calibrated joint limits and pose libraries
│   ├── vision.py        # MediaPipe gesture detection and boxing AI logic
│   ├── choreography.py  # Symphony and dance choreography routines
│   └── cli.py           # Command line entry point ('baxter')
├── examples/            # Standalone runnable scripts
├── models/              # Pretrained gesture model and audio tracks
├── pyproject.toml       # Build configuration and dependencies
├── setup.py             # Setup script
└── README.md
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
