from setuptools import setup, find_packages

setup(
    name="baxter-py",
    version="1.0.0",
    description="Modern, ROS-Agnostic Python Library and CLI for Rethink Robotics Baxter",
    author="Dafodilrat",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "websockets>=10.0",
        "numpy>=1.20,<2.0",
        "opencv-python-headless>=4.5.0",
        "pillow>=8.0.0",
    ],
    extras_require={
        "vision": ["mediapipe>=0.10.0"],
    },
    entry_points={
        "console_scripts": [
            "baxter=baxter.cli:main",
        ],
    },
    include_package_data=True,
    python_requires=">=3.8",
)
