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

    # If local checkpoint directory is provided, ensure offline mode to avoid hub timeouts
    if os.path.isdir(checkpoint_path):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

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
                repetition_penalty=1.15,
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

            raw_text = tokenizer.batch_decode(seq, skip_special_tokens=True)[0]
            text_output = clean_vlm_text_output(raw_text)

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

        return text_output, elapsed_ms, logit_conf
    except Exception as e:
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message=f"RSUniVLM inference execution failed: {e}",
            detail=str(e),
        )


# Re-export pure parsing utilities from parsing.py
from ai_service.rsunivlm.parsing import (
    resolve_detection_mode,
    extract_water_spectral_mask,
    extract_coastline_contour,
    parse_segmentation_output,
    parse_bounding_boxes,
    create_overlay_image,
    image_to_base64,
    mask_to_base64,
    clean_vlm_text_output,
)
