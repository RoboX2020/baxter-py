"""
Baxter-Py: Modern, ROS-Agnostic Python Library and CLI for Rethink Robotics Baxter.
Communicates natively via high-speed Rosbridge WebSockets.
"""

from .client import Baxter
from .poses import POSES, JOINTS, LIMITS
from .limb import Limb
from .head import Head
from .display import Display
from .camera import Camera
from .choreography import SymphonyChoreography, DanceParty
from .vision import BoxerSparring
from .arena import InteractiveArena
from .sim import broadcast_sim_command, launch_sim_twin

__version__ = "1.1.0"
__all__ = [
    "Baxter",
    "Limb",
    "Head",
    "Display",
    "Camera",
    "BoxerSparring",
    "InteractiveArena",
    "SymphonyChoreography",
    "DanceParty",
    "broadcast_sim_command",
    "launch_sim_twin",
    "POSES",
    "JOINTS",
    "LIMITS",
]
