"""
Sliding-window chip tiling & high-resolution inference engine for SatQuery AI.

Handles:
1. Grid / sliding-window chip generation with configurable overlap.
2. Windowed raster reads without loading multi-GB images into memory.
3. Coordinate translation (tile-local -> full-scene global pixel coordinates).
4. IoU-based Non-Maximum Suppression (NMS) and box merging for seam artifacts.
5. Tiled inference orchestration for high-resolution detection.
"""

from dataclasses import dataclass
import logging
from typing import Callable, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class ChipWindow:
    col_off: int
    row_off: int
    width: int
    height: int
    chip_index: int


def generate_sliding_windows(
    width: int,
    height: int,
    chip_size: int = 1024,
    overlap_ratio: float = 0.15,
) -> List[ChipWindow]:
    """
    Generates an overlapping grid of window coordinates covering the entire raster.
    Guarantees full coverage of the image, including the right/bottom boundaries.
    """
    if width <= chip_size and height <= chip_size:
        return [ChipWindow(col_off=0, row_off=0, width=width, height=height, chip_index=0)]

    stride = max(1, int(chip_size * (1.0 - overlap_ratio)))

    # Compute row offsets
    row_offsets = list(range(0, max(1, height - chip_size + 1), stride))
    if not row_offsets or row_offsets[-1] + chip_size < height:
        row_offsets.append(max(0, height - chip_size))
    row_offsets = sorted(list(set(row_offsets)))

    # Compute col offsets
    col_offsets = list(range(0, max(1, width - chip_size + 1), stride))
    if not col_offsets or col_offsets[-1] + chip_size < width:
        col_offsets.append(max(0, width - chip_size))
    col_offsets = sorted(list(set(col_offsets)))

    windows: List[ChipWindow] = []
    idx = 0
    for r_off in row_offsets:
        w_h = min(chip_size, height - r_off)
        for c_off in col_offsets:
            w_w = min(chip_size, width - c_off)
            windows.append(
                ChipWindow(
                    col_off=c_off,
                    row_off=r_off,
                    width=w_w,
                    height=w_h,
                    chip_index=idx,
                )
            )
            idx += 1

    return windows


def calculate_iou(box1: List[int], box2: List[int]) -> float:
    """
    Calculates Intersection-over-Union (IoU) between two bounding boxes [x1, y1, x2, y2].
    """
    x1_a, y1_a, x2_a, y2_a = box1[:4]
    x1_b, y1_b, x2_b, y2_b = box2[:4]

    inter_x1 = max(x1_a, x1_b)
    inter_y1 = max(y1_a, y1_b)
    inter_x2 = min(x2_a, x2_b)
    inter_y2 = min(y2_a, y2_b)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0, x2_a - x1_a) * max(0, y2_a - y1_a)
    area_b = max(0, x2_b - x1_b) * max(0, y2_b - y1_b)
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return float(inter_area / union_area)


def translate_box_to_global(
    box: List[int],
    col_off: int,
    row_off: int,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> List[int]:
    """
    Translates a box [x1, y1, x2, y2] from tile-local coordinates to full-scene coordinates.
    """
    x1, y1, x2, y2 = box[:4]
    gx1 = int(round(x1 * scale_x + col_off))
    gy1 = int(round(y1 * scale_y + row_off))
    gx2 = int(round(x2 * scale_x + col_off))
    gy2 = int(round(y2 * scale_y + row_off))
    return [gx1, gy1, gx2, gy2]


def apply_nms(
    boxes: List[List[int]],
    confidences: Optional[List[float]] = None,
    iou_threshold: float = 0.40,
    merge_overlapping: bool = True,
) -> Tuple[List[List[int]], List[float]]:
    """
    Applies Non-Maximum Suppression (NMS) and merges overlapping bounding boxes across tile borders.
    Returns:
        (filtered_boxes, filtered_confidences)
    """
    if not boxes:
        return [], []

    if confidences is None or len(confidences) != len(boxes):
        confidences = [1.0] * len(boxes)

    # Sort boxes by confidence in descending order
    order = sorted(range(len(boxes)), key=lambda i: confidences[i], reverse=True)

    kept_boxes: List[List[int]] = []
    kept_confidences: List[float] = []

    used = [False] * len(boxes)

    for i_idx in range(len(order)):
        i = order[i_idx]
        if used[i]:
            continue

        curr_box = list(boxes[i])
        curr_conf = confidences[i]
        used[i] = True

        # Check for overlaps with remaining boxes
        for j_idx in range(i_idx + 1, len(order)):
            j = order[j_idx]
            if used[j]:
                continue

            iou = calculate_iou(curr_box, boxes[j])
            if iou > iou_threshold:
                used[j] = True
                if merge_overlapping:
                    # Merge bounding boxes: union of bounds
                    curr_box[0] = min(curr_box[0], boxes[j][0])
                    curr_box[1] = min(curr_box[1], boxes[j][1])
                    curr_box[2] = max(curr_box[2], boxes[j][2])
                    curr_box[3] = max(curr_box[3], boxes[j][3])
                    curr_conf = max(curr_conf, confidences[j])

        kept_boxes.append(curr_box)
        kept_confidences.append(float(round(curr_conf, 2)))

    return kept_boxes, kept_confidences


def run_tiled_detection(
    raster_source: Union[bytes, str],
    query: str,
    detection_fn: Callable[[Image.Image, str], dict],
    chip_size: int = 1024,
    overlap_ratio: float = 0.15,
    max_chips: int = 25,
) -> dict:
    """
    Executes high-resolution sliding-window detection across a large raster.

    Args:
        raster_source: File path or raw bytes of the GeoTIFF/JP2 raster.
        query: User text prompt for detection.
        detection_fn: Function executing detection on a PIL Image (e.g., run_detection).
        chip_size: Pixel size of square chips.
        overlap_ratio: Overlap percentage between adjacent chips.
        max_chips: Safety limit on total chips to prevent runaway latency.

    Returns:
        DetectionResult dict with aggregated boxes in full-scene pixel coordinates.
    """
    from app.geotiff import get_geotiff_info, read_geotiff_window, process_geotiff

    # 1. Inspect raster metadata
    geo_meta = get_geotiff_info(raster_source)
    if not geo_meta:
        # Fallback to standard process if not a valid georaster
        if isinstance(raster_source, bytes):
            img, _ = process_geotiff(raster_source)
            return detection_fn(img, query)
        else:
            with open(raster_source, "rb") as f:
                img, _ = process_geotiff(f.read())
            return detection_fn(img, query)

    raw_w, raw_h = geo_meta.raw_size

    # If image is small enough, run single detection directly
    if max(raw_w, raw_h) <= chip_size:
        img, _ = process_geotiff(raster_source)
        return detection_fn(img, query)

    # 2. Generate sliding windows
    windows = generate_sliding_windows(
        width=raw_w,
        height=raw_h,
        chip_size=chip_size,
        overlap_ratio=overlap_ratio,
    )

    if len(windows) > max_chips:
        logger.warning(
            "Tiling generated %d chips (exceeds safety limit %d). Sub-sampling to max chips.",
            len(windows),
            max_chips,
        )
        step = max(1, len(windows) // max_chips)
        windows = windows[::step][:max_chips]

    logger.info("Executing high-resolution tiled detection across %d chips for query: %r", len(windows), query)

    all_boxes: List[List[int]] = []
    all_confs: List[float] = []
    total_latency_ms = 0
    sub_tool_used = "rsunivlm_det_tiled"

    # 3. Process each window chip
    for idx, win in enumerate(windows):
        logger.info(
            "Scanning chip %d/%d (col: %d, row: %d, size: %dx%d)...",
            idx + 1,
            len(windows),
            win.col_off,
            win.row_off,
            win.width,
            win.height,
        )
        chip_img = read_geotiff_window(
            raster_source,
            col_off=win.col_off,
            row_off=win.row_off,
            width=win.width,
            height=win.height,
        )
        if not chip_img:
            continue

        try:
            chip_res = detection_fn(chip_img, query)
            lat = chip_res.get("meta", {}).get("latency_ms", 0)
            total_latency_ms += lat
            sub_tool_used = chip_res.get("meta", {}).get("tool_used", "rsunivlm_det_tiled")

            boxes = chip_res.get("boxes") or []
            conf = chip_res.get("confidence", 0.80)

            # Translate local box coordinates to global full-scene coordinates
            scale_x = win.width / float(chip_img.width) if chip_img.width > 0 else 1.0
            scale_y = win.height / float(chip_img.height) if chip_img.height > 0 else 1.0

            for b in boxes:
                gb = translate_box_to_global(
                    box=b,
                    col_off=win.col_off,
                    row_off=win.row_off,
                    scale_x=scale_x,
                    scale_y=scale_y,
                )
                all_boxes.append(gb)
                all_confs.append(conf)

        except Exception as exc:
            logger.warning("Chip %d (%d, %d) detection failed: %s", win.chip_index, win.col_off, win.row_off, exc)

    # 4. Apply Non-Maximum Suppression (NMS) to merge overlapping seam boxes
    merged_boxes, merged_confs = apply_nms(
        boxes=all_boxes,
        confidences=all_confs,
        iou_threshold=0.35,
        merge_overlapping=True,
    )

    # 5. Normalize boxes to [0, 1000] coordinate space for frontend SVG rendering
    normalized_boxes: List[List[int]] = []
    for b in merged_boxes:
        nx1 = int(round(b[0] / float(raw_w) * 1000.0))
        ny1 = int(round(b[1] / float(raw_h) * 1000.0))
        nx2 = int(round(b[2] / float(raw_w) * 1000.0))
        ny2 = int(round(b[3] / float(raw_h) * 1000.0))
        nx1 = max(0, min(1000, nx1))
        ny1 = max(0, min(1000, ny1))
        nx2 = max(0, min(1000, nx2))
        ny2 = max(0, min(1000, ny2))
        normalized_boxes.append([nx1, ny1, nx2, ny2])

    avg_conf = float(np.mean(merged_confs)) if merged_confs else 0.80

    return {
        "mode": "bbox",
        "boxes": normalized_boxes,
        "confidence": float(round(avg_conf, 2)),
        "meta": {
            "tool_used": sub_tool_used if sub_tool_used in ("rsunivlm_vg", "rsunivlm_seg") else "rsunivlm_vg",
            "parameters": {
                "tiling": {
                    "enabled": True,
                    "total_chips": len(windows),
                    "chip_size": chip_size,
                    "overlap_ratio": overlap_ratio,
                    "raw_dimensions": [raw_w, raw_h],
                    "raw_detections_before_nms": len(all_boxes),
                    "detections_after_nms": len(normalized_boxes),
                },
            },
            "latency_ms": total_latency_ms,
        },
    }
