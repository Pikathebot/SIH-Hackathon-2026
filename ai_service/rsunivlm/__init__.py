"""
RSUniVLM Vision-Language Model Module for Remote Sensing.
Conditionally exports real inference wrapper or contract mock based on AI_SERVICE_MODE.
"""

import os

if os.environ.get("AI_SERVICE_MODE") == "real":
    from .wrapper import run_vqa, run_captioning, run_detection, run_change_detection
else:
    from .mock import run_vqa, run_captioning, run_detection, run_change_detection

__all__ = [
    "run_vqa",
    "run_captioning",
    "run_detection",
    "run_change_detection",
]
