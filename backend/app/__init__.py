"""SatQuery AI Backend — app package."""

import sys
from pathlib import Path

# Add project root to sys.path so ai_service and other root packages are importable
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

