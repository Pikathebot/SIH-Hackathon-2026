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
    Extracts high-contrast binary water body mask using optical spectral ratios
    and single-band absorption characteristics (e.g. Sentinel-2 Band 8 NIR, SAR, Panchromatic).
    Identifies oceans, coastal waters, rivers, lakes, reservoirs, and flood extent while rejecting vegetation and dry soil.
    """
    img_np = np.array(image_pil.convert("RGB"), dtype=np.float32) / 255.0
    R = img_np[:, :, 0]
    G = img_np[:, :, 1]
    B = img_np[:, :, 2]
    eps = 1e-6

    # Max-min channel dispersion (color difference / saturation proxy)
    max_c = np.maximum(np.maximum(R, G), B)
    min_c = np.minimum(np.minimum(R, G), B)
    spread = max_c - min_c
    brightness = (R + G + B) / 3.0

    # Detect if raster is single-band grayscale / NIR (B08) / SAR
    is_grayscale = float(np.mean(spread)) < 0.03

    if is_grayscale:
        # For single-channel NIR (e.g. Sentinel-2 B08) and SAR rasters:
        # Water absorption creates near-zero reflectance / specular backscatter (< 0.22)
        # Land and vegetation have strong NIR reflectance / diffuse scattering (> 0.30)
        water_condition = (brightness < 0.22)
    else:
        # Normalized Difference Water Index (NDWI proxy: Blue - Red) and Blue-Green ratio
        blue_ratio = (B - R) / (B + R + eps)
        blue_green_ratio = (B - G) / (B + G + eps)

        # 1. Coastal / River / Shallow water: clear blue/cyan dominance, low red, positive blue-to-red contrast
        coastal_river_water = (
            (blue_ratio > 0.06) &
            (blue_green_ratio > -0.30) &
            (brightness < 0.60) &
            (R < 0.25) &
            (B > R)
        )

        # 2. Deep ocean / clear dark water: tightly constrained against terrestrial shadows & asphalt:
        deep_dark_water = (
            (brightness < 0.16) &
            (R < 0.08) &
            (B > R + 0.01) &
            (G >= R) &
            (spread < 0.08) &
            (blue_ratio > 0.10)
        )

        water_condition = coastal_river_water | deep_dark_water

    mask = np.zeros((image_pil.height, image_pil.width), dtype=np.uint8)
    mask[water_condition] = 255

    # Clean isolated speckles with morphology
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def extract_coastline_contour(water_mask: np.ndarray, thickness: int = 2) -> np.ndarray:
    """
    Extracts the sharp 1D/2D land-water interface boundary / coastline contour from a water mask.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(water_mask, kernel, iterations=thickness)
    eroded = cv2.erode(water_mask, kernel, iterations=thickness)
    contour = cv2.subtract(dilated, eroded)
    return contour


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


def clean_vlm_text_output(text: str) -> str:
    """
    Sanitizes raw autoregressive VLM text output:
    1. Truncates at conversation template delimiters (###, <|im_end|>, User:, Assistant:)
    2. Strips leading task tags ([VQA], [CCD], etc.)
    3. Detects and trims repetitive token/phrase cycles
    4. Normalizes punctuation spacing and whitespace
    """
    if not text:
        return ""

    # 1. Truncate at common chat/template delimiters and stop sequences
    stop_patterns = [
        r"###",
        r"<\|im_end\|>",
        r"<\|endoftext\|>",
        r"\bUser:",
        r"\bAssistant:",
        r"\bHuman:",
        r"\bQuestion:",
    ]
    cleaned = text
    for pat in stop_patterns:
        match = re.search(pat, cleaned, flags=re.IGNORECASE)
        if match:
            cleaned = cleaned[:match.start()]

    # 2. Clean leading/trailing task tags if leaked into response
    cleaned = re.sub(r"^\s*\[(VQA|CAP|CCD|SEG|DET|VG|REF)\]\s*", "", cleaned, flags=re.IGNORECASE)

    # 3. Detect and remove repeating token/phrase cycles (e.g. '### 2410 ### 2410' or 'word word word')
    words = cleaned.strip().split()
    if len(words) > 6:
        for n in range(1, min(15, len(words) // 2)):
            for i in range(len(words) - 2 * n):
                chunk1 = words[i : i + n]
                chunk2 = words[i + n : i + 2 * n]
                chunk3 = words[i + 2 * n : i + 3 * n] if i + 3 * n <= len(words) else None
                if chunk1 == chunk2 and (chunk3 is None or chunk1 == chunk3):
                    words = words[: i + n]
                    break
        cleaned = " ".join(words)

    # 4. Clean extra whitespace around punctuation
    cleaned = re.sub(r"\s+([.,!?;])", r"\1", cleaned)
    return cleaned.strip()