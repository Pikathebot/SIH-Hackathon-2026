"""
Internal data classes for database rows.

These represent rows in the SQLite tables defined by DATABASE_CONTRACT.md v1.0.0.
They are internal to the backend — never exposed directly in API responses.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageRow:
    """Maps to the `images` table — DATABASE_CONTRACT.md §1."""
    id: str                         # UUID v4
    modality: str                   # "optical" | "sar"
    capture_date: Optional[str]     # ISO-8601 date, nullable
    storage_path: str               # relative path under backend/data/images/
    checksum: str                   # SHA-256
    created_at: str                 # ISO-8601 UTC timestamp


@dataclass
class QueryRow:
    """Maps to the `queries` table — DATABASE_CONTRACT.md §1."""
    id: str                         # UUID v4
    query_text: str
    image_ids: str                  # JSON-encoded array of image IDs
    selected_task: str              # canonical task enum
    tool_used: str                  # canonical tool_used enum
    parameters: Optional[str]       # JSON-encoded object
    answer: Optional[str]
    confidence: float               # 0.0-1.0
    visual_evidence_type: str       # "none" | "bbox" | "mask"
    visual_evidence_ref: Optional[str]  # path to overlay/mask image
    latency_ms: int
    inputs_validated: int           # 0 or 1 (SQLite boolean)
    status: str                     # "success" | "error"
    error_code: Optional[str]
    created_at: str                 # ISO-8601 UTC timestamp
