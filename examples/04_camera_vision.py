#!/usr/bin/env python3
"""
Example 04: Head Camera Streaming & MediaPipe Gesture Recognition.
Captures live camera frames and classifies hand gestures in real-time.
"""

import asyncio
import cv2
from baxter import Baxter
from baxter.vision import GestureDetector

async def main():
    detector = GestureDetector()

    async with Baxter() as robot:
        print("Acquiring 10 frames from head camera...")
        count = 0
        async for frame in robot.camera.stream("head_camera"):
            count += 1
            detections = detector.detect(frame)
            if detections:
                top = detections[0]
                print(f"Frame {count:02d}: Detected '{top['gesture']}' (confidence: {top['score']:.2f}) at wrist {top['wrist']}")
            else:
                print(f"Frame {count:02d}: No hands detected in view.")

            if count >= 10:
                cv2.imwrite("head_camera_sample.jpg", frame)
                print("Saved sample frame to head_camera_sample.jpg")
                break

if __name__ == "__main__":
    asyncio.run(main())
