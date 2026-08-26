"""
Optical-SAR Multi-Sensor Fusion Module.
Conditionally exports real heuristic fusion or contract mock based on AI_SERVICE_MODE.
"""

import os

if os.environ.get("AI_SERVICE_MODE") == "real":
    from .wrapper import run_fusion
else:
    from .mock import run_fusion

__all__ = ["run_fusion"]
