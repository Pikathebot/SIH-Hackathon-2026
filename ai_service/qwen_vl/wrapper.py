"""
Qwen-VL engine — implements the same function contract as
`ai_service/rsunivlm/wrapper.py` (AI_SERVICE_CONTRACT.md §2) on top of a
general-purpose vision-language model served by llama.cpp llama-server (Qwen3-VL-8B GGUF).

What this engine does well: free-form VQA, scene captioning, box grounding
(Qwen3-VL emits `bbox_2d` in a 0-1000 normalised frame) and describing changes.
What it cannot do: pixel-level segmentation. For mask-mode detection we use the
spectral water/land/coastline extractors from `rsunivlm/parsing.py` when the
query is about those surfaces, otherwise we rasterise the grounded boxes into a
mask and say so in `meta.parameters.mask_source`.

Confidence honesty (contract §2): when the server returns token logprobs we
report their mean probability as `confidence_source: "model_softmax"`; the
fixed fall-back values below are labelled `"heuristic"`.
"""

from __future__ import annotations

import json
import re
from typing import Literal, Optional

import cv2
import numpy as np
from PIL import Image

from ai_service.common.errors import AIServiceError, MODEL_INFERENCE_FAILED
from ai_service.common.types import CaptioningResult, ChangeResult, DetectionResult, VQAResult
from ai_service.qwen_vl.client import ChatResult, get_client
from ai_service.rsunivlm.parsing import (
    clean_vlm_text_output,
    create_overlay_image,
    extract_coastline_contour,
    extract_water_spectral_mask,
    image_to_base64,
    mask_to_base64,
    resolve_detection_mode,
)

# Heuristic confidences used ONLY when the model server returns no logprobs.
HEURISTIC_CONF = {"vqa": 0.80, "cap": 0.80, "vg": 0.70, "vg_empty": 0.40, "seg": 0.70, "ccd": 0.75}

SYSTEM_PROMPT = (
    "You are SatQuery, an expert remote-sensing image analyst. Images are satellite or aerial "
    "scenes (optical RGB/multispectral composites or SAR backscatter, where bright = strong "
    "return, dark = smooth surfaces such as calm water). Answer precisely and concisely, "
    "ground every claim in visible evidence, and say so when something cannot be determined."
)

_LAND = ("landmass", "land mass", "land", "terrain", "ground")
_COAST = ("coast", "coastline", "coastal", "shore", "shoreline", "waterline", "land-water")
_WATER = ("water", "river", "lake", "flood", "reservoir", "ocean", "sea", "stream")


def _check_image(*images: Image.Image) -> None:
    for im in images:
        if not isinstance(im, Image.Image):
            raise AIServiceError(MODEL_INFERENCE_FAILED, "Invalid image input: expected PIL.Image.Image instance")


def _conf(res: ChatResult, key: str) -> tuple[float, str]:
    if res.token_confidence is not None:
        return round(max(0.0, min(1.0, res.token_confidence)), 2), "model_softmax"
    return HEURISTIC_CONF[key], "heuristic"


def _model_name() -> str:
    return get_client().model


# --------------------------------------------------------------------------- VQA
def run_vqa(image: Image.Image, question: str) -> VQAResult:
    _check_image(image)
    res = get_client().chat(question.strip(), images=[image], system=SYSTEM_PROMPT, max_tokens=384)
    conf, src = _conf(res, "vqa")
    return {
        "answer": clean_vlm_text_output(res.text) or "No response generated.",
        "confidence": conf,
        "meta": {
            "tool_used": "qwen_vl_vqa",
            "parameters": {"model": _model_name(), "question": question, "confidence_source": src},
            "latency_ms": res.latency_ms,
        },
    }


# --------------------------------------------------------------------- Captioning
def run_captioning(image: Image.Image) -> CaptioningResult:
    _check_image(image)
    prompt = (
        "Describe this remote-sensing scene in 3-5 sentences: dominant land cover, water bodies, "
        "built-up areas and infrastructure, vegetation, terrain, and any notable objects."
    )
    res = get_client().chat(prompt, images=[image], system=SYSTEM_PROMPT, max_tokens=384)
    conf, src = _conf(res, "cap")
    return {
        "caption": clean_vlm_text_output(res.text) or "Land cover scene observed.",
        "confidence": conf,
        "meta": {
            "tool_used": "qwen_vl_cap",
            "parameters": {"model": _model_name(), "confidence_source": src},
            "latency_ms": res.latency_ms,
        },
    }


# ---------------------------------------------------------------------- Grounding
def _norm1000_to_pixels(bbox: list, size: tuple[int, int]) -> Optional[list[int]]:
    """Qwen3-VL boxes are [x1,y1,x2,y2] in a 0-1000 frame; map to pixel ints."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    w, h = size
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    px = [
        int(round(max(0.0, min(1000.0, x1)) * w / 1000.0)),
        int(round(max(0.0, min(1000.0, y1)) * h / 1000.0)),
        int(round(max(0.0, min(1000.0, x2)) * w / 1000.0)),
        int(round(max(0.0, min(1000.0, y2)) * h / 1000.0)),
    ]
    if px[2] - px[0] < 1 or px[3] - px[1] < 1:
        return None
    return px


_BOX_OBJ_RE = re.compile(r"\{[^{}]*\"bbox_2d\"[^{}]*\}")


def _parse_native_boxes(text: str) -> list[dict]:
    """Extract Qwen3-VL native grounding objects from free-form output.

    Tolerates code fences, surrounding prose and a list truncated by max_tokens
    (each complete `{... "bbox_2d": [...] ...}` object is parsed on its own).
    """
    objs = []
    for m in _BOX_OBJ_RE.finditer(text or ""):
        try:
            o = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(o, dict):
            objs.append(o)
    return objs


def ground_boxes(image: Image.Image, query: str) -> tuple[list[list[int]], list[str], ChatResult]:
    # Qwen3-VL's trained grounding format is a bare JSON list of
    # {"bbox_2d": [...], "label": ...}. Measured on sample_data (2026-11-01): wrapping it in
    # {"objects": [...]}, forcing a strict JSON grammar and adding the cautious analyst
    # system prompt made the model return [] even for clearly visible ships, so grounding
    # runs unconstrained, without the system prompt, and is parsed leniently.
    # Phrasing follows the Qwen3-VL grounding cookbook; offering an explicit "[] if none"
    # escape made empty answers more likely in testing.
    prompt = (
        f"{query.strip()}\n"
        "Locate every object in the image that this refers to and output its bbox coordinates "
        'using JSON format, as a list of {"bbox_2d": [x1, y1, x2, y2], "label": str}.'
    )
    res = get_client().chat(prompt, images=[image], max_tokens=1024)
    boxes, labels = [], []
    for obj in _parse_native_boxes(res.text):
        px = _norm1000_to_pixels(obj.get("bbox_2d"), image.size)
        if px is not None:
            boxes.append(px)
            labels.append(str(obj.get("label", "object")))
    return boxes, labels, res


def _spectral_mask(image: Image.Image, q_lower: str) -> tuple[Optional[np.ndarray], Optional[str], tuple]:
    if any(w in q_lower for w in _LAND):
        water = extract_water_spectral_mask(image)
        return cv2.bitwise_not(water), "landmass", (0, 220, 100)
    if any(w in q_lower for w in _COAST):
        water = extract_water_spectral_mask(image)
        return extract_coastline_contour(water, thickness=3), "coastline", (0, 240, 255)
    if any(w in q_lower for w in _WATER):
        return extract_water_spectral_mask(image), "water", (0, 120, 255)
    return None, None, (255, 80, 0)


def run_detection(
    image: Image.Image,
    query: str,
    mode: Literal["auto", "bbox", "mask"] = "auto",
) -> DetectionResult:
    _check_image(image)
    resolved_mode = resolve_detection_mode(query, mode=mode)

    if resolved_mode == "bbox":
        boxes, labels, res = ground_boxes(image, query)
        conf, src = _conf(res, "vg" if boxes else "vg_empty")
        return {
            "mode": "bbox",
            "boxes": boxes,
            "mask_base64": None,
            "overlay_base64": None,
            "confidence": conf,
            "meta": {
                "tool_used": "qwen_vl_vg",
                "parameters": {
                    "model": _model_name(),
                    "resolved_mode": "bbox",
                    "detected_labels": sorted(set(labels)),
                    "confidence_source": src,
                },
                "latency_ms": res.latency_ms,
            },
        }

    # ---- mask mode: spectral extractor for water/land/coast, else rasterised boxes
    mask, label, color = _spectral_mask(image, query.lower())
    latency_ms = 0
    if mask is not None:
        mask_source = "spectral_index"
        conf, src = HEURISTIC_CONF["seg"], "heuristic"
        labels = [label]
    else:
        boxes, labels, res = ground_boxes(image, query)
        latency_ms = res.latency_ms
        mask = np.zeros((image.size[1], image.size[0]), dtype=np.uint8)
        for x1, y1, x2, y2 in boxes:
            mask[y1:y2, x1:x2] = 255
        mask_source = "bbox_rasterized"
        conf, src = _conf(res, "seg" if boxes else "vg_empty")

    if np.any(mask > 0):
        overlay_b64 = image_to_base64(create_overlay_image(image, mask, color=color, alpha=0.5))
    else:
        overlay_b64 = image_to_base64(image)

    return {
        "mode": "mask",
        "boxes": None,
        "mask_base64": mask_to_base64(mask),
        "overlay_base64": overlay_b64,
        "confidence": conf,
        "meta": {
            "tool_used": "qwen_vl_seg",
            "parameters": {
                "model": _model_name(),
                "resolved_mode": "mask",
                "mask_source": mask_source,
                "detected_labels": sorted(set(labels)),
                "confidence_source": src,
            },
            "latency_ms": latency_ms,
        },
    }


# --------------------------------------------------------------- Change detection
def _diff_mask(before: Image.Image, after: Image.Image) -> Optional[np.ndarray]:
    a = np.array(before.convert("RGB"))
    b = np.array(after.convert("RGB").resize(before.size))
    gray = cv2.cvtColor(cv2.absdiff(a, b), cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return mask


def run_change_detection(
    image_before: Image.Image,
    image_after: Image.Image,
    query: Optional[str] = None,
) -> ChangeResult:
    _check_image(image_before, image_after)
    q = query.strip() if query else "Describe the changes between these two images."
    prompt = (
        "The first image was acquired BEFORE, the second AFTER, over the same area. "
        f"{q}\nDescribe concrete changes (new/removed structures, vegetation loss or gain, water "
        "extent, land-use conversion) and where in the frame they occur. If nothing changed, say so."
    )
    res = get_client().chat(prompt, images=[image_before, image_after], system=SYSTEM_PROMPT, max_tokens=512)
    conf, src = _conf(res, "ccd")

    mask = _diff_mask(image_before, image_after)
    mask_b64 = overlay_b64 = None
    if mask is not None:
        mask_b64 = mask_to_base64(mask)
        overlay_b64 = image_to_base64(
            create_overlay_image(image_after.resize(image_before.size), mask, color=(255, 0, 0), alpha=0.5)
        )

    return {
        "answer": clean_vlm_text_output(res.text) or "Changes detected between the two timeframes.",
        "mask_base64": mask_b64,
        "overlay_base64": overlay_b64,
        "confidence": conf,
        "meta": {
            "tool_used": "qwen_vl_ccd",
            "parameters": {"model": _model_name(), "query": query, "mask_source": "pixel_difference", "confidence_source": src},
            "latency_ms": res.latency_ms,
        },
    }


# --------------------------------------------------------------- Intent routing
_TASKS = ["vqa", "captioning", "detection", "change_detection", "fusion"]
_INTENT_SCHEMA = {
    "type": "object",
    "properties": {"task": {"type": "string", "enum": _TASKS}},
    "required": ["task"],
}


def classify_intent(query: str, modalities: list[str]) -> Optional[str]:
    """Ask the LLM which canonical task a query maps to. Returns None on any failure
    so the caller can fall back to the keyword classifier."""
    prompt = (
        f"User query about {len(modalities)} satellite image(s) with modalities {modalities}:\n"
        f'"{query.strip()}"\n'
        "Pick exactly one task:\n"
        "- vqa: a question to be answered in words (counts, yes/no, what/which/how).\n"
        "- captioning: describe or summarise the whole scene.\n"
        "- detection: localise, find, box, highlight, segment or map specific objects/surfaces.\n"
        "- change_detection: compare two optical images over time.\n"
        "- fusion: combine one optical and one SAR image.\n"
        'Return JSON {"task": "..."}.'
    )
    try:
        data, _ = get_client().chat_json(prompt, _INTENT_SCHEMA, max_tokens=32, temperature=0.0)
        task = data.get("task") if isinstance(data, dict) else None
        return task if task in _TASKS else None
    except Exception:
        return None
