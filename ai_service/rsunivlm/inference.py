"""
Core inference and output-parsing utilities for RSUniVLM.
Wraps the vendored LLaVA-NeXT-based model architecture.
"""

import base64
import copy
import io
import os
import re
import sys
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
import torch

# Ensure vendored llava package is importable
VENDOR_DIR = os.path.join(os.path.dirname(__file__), "vendor")
if VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)

from llava.model.builder import load_pretrained_model
from llava.mm_utils import process_images, tokenizer_image_token
from llava.conversation import conv_templates
from llava.constants import IMAGE_TOKEN_INDEX
from ai_service.common.errors import AIServiceError, MODEL_INFERENCE_FAILED


def left_pad_sequences(sequences, desired_length, padding_value):
    """Pads token sequences on the left to matching maximum length."""
    return tuple(
        [padding_value] * (desired_length - len(seq)) + list(seq)
        for seq in sequences
    )


def load_rsunivlm_model(
    checkpoint_path: str,
    lora_adapter_path: Optional[str] = None,
) -> Tuple[object, object, object]:
    """
    Loads tokenizer, model, and image processor from checkpoint path.
    Optionally attaches LoRA adapter if specified.
    """
    if not os.path.exists(checkpoint_path):
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message=f"RSUniVLM checkpoint not found at: {checkpoint_path}",
            detail="Ensure RSUNIVLM_CHECKPOINT_PATH points to a valid weights directory.",
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_name = "llava_qwen_gmoe"
    llava_model_args = {
        "multimodal": True,
        "attn_implementation": "sdpa" if hasattr(torch.nn.functional, "scaled_dot_product_attention") else None,
    }

    try:
        tokenizer, model, image_processor, _ = load_pretrained_model(
            checkpoint_path,
            model_base=None,
            model_name=model_name,
            torch_dtype="float16" if device == "cuda" else "float32",
            device_map="auto" if device == "cuda" else None,
            **llava_model_args,
        )
        model.eval()

        # Load LoRA adapter if path provided and exists
        if lora_adapter_path and os.path.exists(lora_adapter_path):
            try:
                from peft import PeftModel
                model = PeftModel.from_pretrained(model, lora_adapter_path)
                model.eval()
            except Exception as e:
                # Log or warn but do not break if LoRA cannot attach
                print(f"[Warning] Failed to load LoRA adapter from {lora_adapter_path}: {e}", file=sys.stderr)

        return tokenizer, model, image_processor
    except Exception as e:
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message=f"Failed to load RSUniVLM model: {e}",
            detail=str(e),
        )


def run_raw_inference(
    model: object,
    tokenizer: object,
    image_processor: object,
    images: List[Image.Image],
    message: str,
    max_new_tokens: int = 1024,
) -> Tuple[str, int, Optional[float]]:
    """
    Executes multimodal generation for 1 or more PIL images and a prompt message.
    Returns (text_output, elapsed_ms, logit_confidence).
    """
    try:
        images_pil = [
            img.convert("RGB").resize((max(img.size[0], 224), max(img.size[1], 224)), Image.Resampling.BICUBIC)
            if (img.size[0] < 224 or img.size[1] < 224)
            else img.convert("RGB")
            for img in images
        ]
        image_tensors = process_images(images_pil, image_processor, model.config)
        image_sizes = [img.size for img in images_pil]

        if len(images) == 1:
            question = "<image>\n" + message
        elif len(images) == 2:
            question = "<image> <image>\n" + message
        else:
            question = ("<image> " * len(images)) + "\n" + message

        # RSUniVLM granularity switch:
        # 2: Pixel-level segmentation ([SEG])
        # 1: Region-level grounding ([VG] / [REF])
        # 0: Image-level VQA / Captioning ([VQA] / [CAP] / [CCD])
        if "[SEG]" in question:
            granularity = 2
        elif "[VG]" in question or "[REF]" in question:
            granularity = 1
        else:
            granularity = 0

        conv = copy.deepcopy(conv_templates["qwen_1_5"])
        conv.append_message(conv.roles[0], question)
        conv.append_message(conv.roles[1], None)
        prompt_question = conv.get_prompt()

        input_id = tokenizer_image_token(prompt_question, tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt")
        input_ids = (input_id,)
        lengths = [len(ids) for ids in input_ids]
        max_len = max(lengths)
        input_ids = left_pad_sequences(input_ids, max_len, tokenizer.pad_token_id)
        input_ids = torch.tensor(input_ids)
        input_ids = input_ids[:, : tokenizer.model_max_length]

        device = next(model.parameters()).device
        dtype = next(model.parameters()).dtype

        start_time = time.time()
        with torch.no_grad():
            image_tensors = [_img.to(dtype=dtype, device=device) for _img in image_tensors]
            gen_out = model.generate(
                input_ids.to(device),
                images=image_tensors,
                image_sizes=image_sizes,
                modalities=["image"] * len(image_sizes),
                do_sample=False,
                temperature=0,
                max_new_tokens=max_new_tokens,
                granularity=granularity,
                return_dict_in_generate=True,
                output_scores=True,
            )

            if hasattr(gen_out, "sequences"):
                seq = gen_out.sequences
                scores = getattr(gen_out, "scores", None)
            else:
                seq = gen_out
                scores = None

            text_output = tokenizer.batch_decode(seq, skip_special_tokens=True)[0]

            logit_conf = None
            if scores:
                try:
                    step_probs = [torch.softmax(s, dim=-1).max(dim=-1).values for s in scores]
                    if step_probs:
                        logit_conf = float(torch.stack(step_probs).mean().item())
                        logit_conf = float(np.clip(logit_conf, 0.50, 0.98))
                except Exception:
                    logit_conf = None

        elapsed_ms = int((time.time() - start_time) * 1000)

        return text_output.strip(), elapsed_ms, logit_conf
    except Exception as e:
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message=f"RSUniVLM inference execution failed: {e}",
            detail=str(e),
        )


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
