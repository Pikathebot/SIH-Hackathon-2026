"""
Pure vision, geometry, and token parsing utilities for RSUniVLM.
This module has zero PyTorch/Transformers dependencies so it can be imported
and tested in lightweight environments without GPU or deep learning packages.
"""

import base64
import io
import re
import sys
from typing import List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image


def extract_water_spectral_mask(image_pil: Image.Image) -> np.ndarray:
    """
    Extracts high-contrast binary water body mask using optical spectral ratios.
    Identifies rivers, lakes, reservoirs, and flood extent while rejecting vegetation and dry soil.
    """
    img_np = np.array(image_pil.convert("RGB"), dtype=np.float32) / 255.0
    R = img_np[:, :, 0]
    G = img_np[:, :, 1]
    B = img_np[:, :, 2]
    eps = 1e-6

    # Normalized Difference Water Index (NDWI proxy: Blue - Red) and Blue-Green ratio
    blue_ratio = (B - R) / (B + R + eps)
    blue_green_ratio = (B - G) / (B + G + eps)
    brightness = (R + G + B) / 3.0

    # Water condition: positive blue-to-red contrast, non-vegetation green balance, low red reflectance
    water_condition = (blue_ratio > 0.05) & (blue_green_ratio > -0.35) & (brightness < 0.65) & (R < 0.40)

    mask = np.zeros((image_pil.height, image_pil.width), dtype=np.uint8)
    mask[water_condition] = 255

    # Clean isolated speckles with morphology
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def parse_segmentation_output(
    output_string: str,
    img_size: Tuple[int, int],
    target_label: Optional[str] = None,
    patch_size: int = 20,
) -> Tuple[Optional[np.ndarray], set]:
    """
    Parses tokenized segmentation output into a 2D binary uint8 mask (0 or 255).
    """
    output_string = output_string.lower().strip()
    try:
        labels = set(re.findall(r"\b[a-z]+(?: [a-z]+)*\b", output_string))
        rows = output_string.split("\n")
        parsed_mask = []
        for row in rows:
            row_data = []
            patches = row.split(", ")
            for patch in patches:
                if "*" in patch:
                    parts = patch.strip().split("*")
                    if len(parts) == 2:
                        label, count = parts[0].strip(), int(parts[1].strip())
                        row_data.extend([label] * count)
            if row_data:
                parsed_mask.append(row_data)

        if not parsed_mask:
            return None, labels

        parsed_mask_np = np.array(parsed_mask)
        height, width = parsed_mask_np.shape

        binary_mask = np.zeros((height * patch_size, width * patch_size), dtype=np.uint8)
        for i in range(height):
            for j in range(width):
                val = parsed_mask_np[i, j].strip()
                if val != "others" and (target_label is None or target_label in val or val in target_label):
                    binary_mask[i * patch_size : (i + 1) * patch_size, j * patch_size : (j + 1) * patch_size] = 255

        binary_mask = cv2.resize(binary_mask, (img_size[0], img_size[1]), interpolation=cv2.INTER_NEAREST)
        return binary_mask, labels
    except Exception as e:
        print(f"Error parsing segmentation mask tokens: {e}", file=sys.stderr)
        return None, set()


def parse_bounding_boxes(
    text_output: str,
    img_size: Tuple[int, int],
) -> List[List[int]]:
    """
    Extracts normalized coordinates [0-100] from text output and scales to pixel coords [x1, y1, x2, y2].
    """
    pred_match = re.findall(r"\[([0-9., ]+)\]", text_output)
    boxes = []
    width, height = img_size
    for match in pred_match:
        try:
            coords = [float(x.strip()) for x in match.split(",") if x.strip()]
            if len(coords) >= 4:
                box = coords[:4]
                x1 = int(round(box[0] / 100.0 * width))
                y1 = int(round(box[1] / 100.0 * height))
                x2 = int(round(box[2] / 100.0 * width))
                y2 = int(round(box[3] / 100.0 * height))
                # Ensure valid bounding box coordinates
                x1, x2 = min(x1, x2), max(x1, x2)
                y1, y2 = min(y1, y2), max(y1, y2)
                boxes.append([x1, y1, x2, y2])
        except Exception:
            continue
    return boxes


def create_overlay_image(
    image_pil: Image.Image,
    binary_mask: np.ndarray,
    color: Tuple[int, int, int] = (0, 0, 255),
    alpha: float = 0.5,
) -> Image.Image:
    """
    Creates a visual overlay with a colored semi-transparent mask on top of the original PIL image.
    """
    img_np = cv2.cvtColor(np.array(image_pil.convert("RGB")), cv2.COLOR_RGB2BGR)
    colored_layer = np.zeros_like(img_np, dtype=np.uint8)
    colored_layer[:] = color
    mask_bool = binary_mask > 128
    overlay = img_np.copy()
    overlay[mask_bool] = cv2.addWeighted(img_np, 1.0 - alpha, colored_layer, alpha, 0.0)[mask_bool]
    return Image.fromarray(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))


def image_to_base64(image_pil: Image.Image, format: str = "PNG") -> str:
    """Encodes a PIL image to a base64 string."""
    buf = io.BytesIO()
    image_pil.save(buf, format=format)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def mask_to_base64(binary_mask: np.ndarray) -> str:
    """Encodes a 2D numpy mask to a base64 grayscale PNG."""
    mask_pil = Image.fromarray(binary_mask, mode="L")
    return image_to_base64(mask_pil, format="PNG")