"""
STEP 1 (after confirming fields with 1_inspect_dataset.py)

Streams N samples from BigEarthNet.txt, saves each image as a JPEG,
and writes an LLaVA-format instruction JSON (the schema RSUniVLM's
llava/train/train.py expects):

[
  {
    "id": "beb_000001",
    "image": "beb_000001.jpg",
    "conversations": [
      {"from": "human", "value": "<image>\nDescribe the land cover visible in this satellite image."},
      {"from": "gpt", "value": "This scene primarily shows Urban fabric, Inland waters, Pastures."}
    ]
  },
  ...
]

Auto-detects two dataset schemas:
  A) BigEarthNet.txt (image-text) — has 'input', 'output', 'type' fields
     → Uses the pre-existing captions/VQA pairs directly
  B) BigEarthNet v2 (classification) — has band images + 'labels'
     → Synthesizes captions from multi-labels

Produces BOTH a captioning-style turn and a VQA-style turn per image,
since the PS requires VQA (mandatory) + one of captioning/grounding.

Usage:
    python 2_prepare_llava_data.py --n_samples 400 --out_dir ./bigearthnet_llava
"""

import argparse
import json
import os
import random
import sys

from datasets import load_dataset
from PIL import Image

# ============================================================================
#  FIELD CONFIGURATION — update these after running 1_inspect_dataset.py
# ============================================================================

# Schema A: BigEarthNet.txt (image-text version)
# If the dataset has these fields, we use pre-built captions/VQA directly.
SCHEMA_A_FIELDS = {
    "image": "image",       # <-- CONFIRM FIELD NAME (the PIL image field)
    "input": "input",       # <-- CONFIRM FIELD NAME (the question/instruction)
    "output": "output",     # <-- CONFIRM FIELD NAME (the answer/caption)
    "type": "type",         # <-- CONFIRM FIELD NAME (e.g. 'captioning', 'binary', 'mcq')
}

# Schema B: BigEarthNet v2 (multi-label classification)
# If schema A fields are missing, fall back to these.
IMAGE_FIELD_CANDIDATES = ["image", "img", "jpg", "png", "s2_image"]  # <-- CONFIRM FIELD NAME
LABEL_FIELD_CANDIDATES = ["labels", "label", "multilabel", "class_labels"]  # <-- CONFIRM FIELD NAME
CAPTION_FIELD_CANDIDATES = ["caption", "text", "description"]  # <-- CONFIRM FIELD NAME (may not exist)

# ============================================================================

DATASET_ID = "BIFOLD-BigEarthNetv2-0/BigEarthNet.txt"

# Captioning question templates (used for Schema B fallback)
QUESTION_TEMPLATES = [
    "Describe the land cover and major features visible in this satellite image.",
    "What types of land cover are present in this image?",
    "Summarize what this remote-sensing image shows.",
    "Identify the main land cover categories in this satellite image.",
    "What does this remote-sensing scene depict?",
]

# VQA templates for binary yes/no questions (Schema B fallback)
VQA_TEMPLATES = [
    ("Does this image contain any built-up or urban areas?", "Urban fabric"),
    ("Is there any water visible in this image?", "Inland waters"),
    ("Does this image show agricultural land?", "Arable land"),
    ("Are there any forest areas in this image?", "Broad-leaved forest"),
    ("Is there any grassland visible in this image?", "Pastures"),
    ("Does this image contain any wetland areas?", "Inland wetlands"),
    ("Are there any industrial areas in this image?", "Industrial or commercial units"),
]

# BigEarthNet v2 canonical 19-class label names
BEN_LABEL_NAMES = [
    "Agro-forestry areas", "Arable land", "Beaches, dunes, sands",
    "Broad-leaved forest", "Coastal wetlands", "Complex cultivation patterns",
    "Coniferous forest", "Industrial or commercial units", "Inland waters",
    "Inland wetlands",
    "Land principally occupied by agriculture, with significant areas of natural vegetation",
    "Marine waters", "Mixed forest",
    "Moors, heathland and sclerophyllous vegetation",
    "Natural grassland and sparsely vegetated areas", "Pastures",
    "Permanent crops", "Transitional woodland, shrub", "Urban fabric",
]


def find_field(sample: dict, candidates: list[str]):
    """Return the first matching field name from candidates, or None."""
    for c in candidates:
        if c in sample:
            return c
    return None


def detect_schema(sample: dict) -> str:
    """Detect whether this is schema A (image-text) or B (classification)."""
    a_fields = SCHEMA_A_FIELDS
    if a_fields["input"] in sample and a_fields["output"] in sample:
        return "A"
    return "B"


def extract_image(sample: dict) -> Image.Image | None:
    """Extract a PIL Image from the sample, trying multiple strategies."""
    # Try schema A image field first
    img_key = SCHEMA_A_FIELDS.get("image")
    if img_key and img_key in sample:
        val = sample[img_key]
        if isinstance(val, Image.Image):
            return val
        if isinstance(val, dict) and "bytes" in val:
            import io
            return Image.open(io.BytesIO(val["bytes"]))

    # Try schema B candidates
    for candidate in IMAGE_FIELD_CANDIDATES:
        if candidate in sample:
            val = sample[candidate]
            if isinstance(val, Image.Image):
                return val
            if isinstance(val, dict) and "bytes" in val:
                import io
                return Image.open(io.BytesIO(val["bytes"]))

    return None


def build_caption_from_labels(labels, label_names=None):
    """Fallback: turn a multi-label list into a template sentence."""
    if label_names is not None and all(isinstance(l, int) for l in labels):
        names = [label_names[i] for i in labels if i < len(label_names)]
    else:
        names = [str(l) for l in labels]
    if not names:
        return "No clearly identifiable land-cover classes are visible in this image."
    return f"This scene primarily shows {', '.join(names[:5])}."


def process_schema_a(sample: dict, sample_id: str, img_path: str) -> list[dict]:
    """
    Process a BigEarthNet.txt sample (has input/output/type).
    Returns a list of LLaVA conversation records.
    """
    records = []
    fields = SCHEMA_A_FIELDS

    instruction = sample.get(fields["input"], "")
    answer = sample.get(fields["output"], "")
    task_type = sample.get(fields["type"], "captioning")

    if not instruction or not answer:
        return []

    # Ensure the instruction references the image token
    if "<image>" not in instruction:
        instruction = f"<image>\n{instruction}"

    records.append({
        "id": sample_id,
        "image": f"images/{sample_id}.jpg",
        "conversations": [
            {"from": "human", "value": instruction},
            {"from": "gpt", "value": answer},
        ],
    })

    # If this was a captioning sample, also create a synthetic VQA turn
    if task_type in ("captioning", "caption"):
        vqa_q, label_hint = random.choice(VQA_TEMPLATES)
        answer_yes = label_hint.lower() in answer.lower()
        vqa_answer = "Yes." if answer_yes else "No."
        records.append({
            "id": f"{sample_id}_vqa",
            "image": f"images/{sample_id}.jpg",
            "conversations": [
                {"from": "human", "value": f"<image>\n{vqa_q}"},
                {"from": "gpt", "value": vqa_answer},
            ],
        })

    return records


def process_schema_b(sample: dict, sample_id: str, img_path: str) -> list[dict]:
    """
    Process a BigEarthNet v2 classification sample (band images + labels).
    Synthesizes captions from multi-labels.
    Returns a list of LLaVA conversation records.
    """
    records = []

    # Get caption
    cap_key = find_field(sample, CAPTION_FIELD_CANDIDATES)
    if cap_key and sample[cap_key]:
        caption = sample[cap_key]
    else:
        label_key = find_field(sample, LABEL_FIELD_CANDIDATES)
        labels = sample[label_key] if label_key else []
        caption = build_caption_from_labels(labels, BEN_LABEL_NAMES)

    # Captioning record
    records.append({
        "id": sample_id,
        "image": f"images/{sample_id}.jpg",
        "conversations": [
            {"from": "human", "value": f"<image>\n{random.choice(QUESTION_TEMPLATES)}"},
            {"from": "gpt", "value": caption},
        ],
    })

    # VQA record
    vqa_q, label_hint = random.choice(VQA_TEMPLATES)
    answer_yes = label_hint.lower() in caption.lower()
    vqa_answer = "Yes." if answer_yes else "No."
    records.append({
        "id": f"{sample_id}_vqa",
        "image": f"images/{sample_id}.jpg",
        "conversations": [
            {"from": "human", "value": f"<image>\n{vqa_q}"},
            {"from": "gpt", "value": vqa_answer},
        ],
    })

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Prepare LLaVA-format training data from BigEarthNet for RSUniVLM LoRA fine-tuning."
    )
    parser.add_argument("--n_samples", type=int, default=400,
                        help="Number of images to process (200-500 recommended for sprint)")
    parser.add_argument("--out_dir", type=str, default="./bigearthnet_llava",
                        help="Output directory for images and train.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset_id", type=str, default=DATASET_ID,
                        help="HuggingFace dataset ID to load")
    args = parser.parse_args()

    random.seed(args.seed)
    img_dir = os.path.join(args.out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    print(f"Loading dataset '{args.dataset_id}' (streaming)...")
    try:
        ds = load_dataset(args.dataset_id, split="train", streaming=True)
    except Exception as e:
        print(f"ERROR loading dataset: {e}")
        print("If this is an auth error, run: huggingface-cli login")
        sys.exit(1)

    # Detect schema from first sample
    it = iter(ds)
    first_sample = next(it)
    schema = detect_schema(first_sample)
    print(f"Detected schema: {'A (image-text)' if schema == 'A' else 'B (classification)'}")
    print(f"Fields found: {list(first_sample.keys())}")

    # Process first sample
    records = []
    n_written = 0
    n_skipped = 0

    def process_sample(sample, sample_id, img_path):
        if schema == "A":
            return process_schema_a(sample, sample_id, img_path)
        else:
            return process_schema_b(sample, sample_id, img_path)

    # Process first sample (already consumed)
    img = extract_image(first_sample)
    if img is not None:
        sample_id = f"beb_{n_written:06d}"
        img_path = os.path.join(img_dir, f"{sample_id}.jpg")
        img.convert("RGB").save(img_path, "JPEG", quality=92)
        new_records = process_sample(first_sample, sample_id, img_path)
        if new_records:
            records.extend(new_records)
            n_written += 1
    else:
        n_skipped += 1

    # Process remaining samples
    while n_written < args.n_samples:
        try:
            sample = next(it)
        except StopIteration:
            print(f"Dataset exhausted early at {n_written} samples.")
            break

        img = extract_image(sample)
        if img is None:
            n_skipped += 1
            if n_skipped <= 5:
                print(f"  WARNING: Skipped sample (no image found). Fields: {list(sample.keys())[:5]}")
            continue

        sample_id = f"beb_{n_written:06d}"
        img_path = os.path.join(img_dir, f"{sample_id}.jpg")

        try:
            img.convert("RGB").save(img_path, "JPEG", quality=92)
        except Exception as e:
            print(f"  WARNING: Failed to save image for sample {n_written}: {e}")
            n_skipped += 1
            continue

        new_records = process_sample(sample, sample_id, img_path)
        if new_records:
            records.extend(new_records)
            n_written += 1
        else:
            n_skipped += 1

        if n_written % 50 == 0:
            print(f"  {n_written}/{args.n_samples} images processed...")

    # Shuffle and write
    random.shuffle(records)
    out_json = os.path.join(args.out_dir, "train.json")
    with open(out_json, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nDone. {n_written} images -> {len(records)} conversation records ({n_skipped} skipped).")
    print(f"Schema used: {'A (image-text)' if schema == 'A' else 'B (classification)'}")
    print(f"Images dir: {img_dir}")
    print(f"JSON file:  {out_json}")
    print(f"\nNext: run 3_train_lora_rsunivlm.sh (WSL) or 3_train_lora_rsunivlm.ps1 (PowerShell),")
    print(f"      pointing --data_path at train.json and --image_folder at the out_dir above.")


if __name__ == "__main__":
    main()
