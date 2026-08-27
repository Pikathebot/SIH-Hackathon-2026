"""
STEP 1: Data Preparation for RSUniVLM LoRA Fine-Tuning

Streams Sentinel-2 satellite samples from EuroSAT / BigEarthNet,
saves each image as a JPEG, and produces an instruction dataset
in LLaVA format (the schema RSUniVLM's llava/train/train.py expects):

[
  {
    "id": "sat_000001_cap",
    "image": "images/sat_000001.jpg",
    "conversations": [
      {"from": "human", "value": "<image>\nDescribe the land cover visible in this satellite image."},
      {"from": "gpt", "value": "This satellite image primarily depicts Forest with dense canopy coverage."}
    ]
  },
  {
    "id": "sat_000001_vqa",
    "image": "images/sat_000001.jpg",
    "conversations": [
      {"from": "human", "value": "<image>\nIs there any forest or dense vegetation visible in this image?"},
      {"from": "gpt", "value": "Yes, this image clearly shows forest cover."}
    ]
  }
]

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

# Default dataset: EuroSAT Sentinel-2 satellite imagery
DEFAULT_DATASET = "resaro/eurosat"

# Human-readable descriptions for the 10 EuroSAT Sentinel-2 land cover categories
CLASS_DESCRIPTIONS = {
    "AnnualCrop": "agricultural annual crop fields and arable farming land",
    "Forest": "dense forest canopy, woodland areas, and natural tree cover",
    "HerbaceousVegetation": "natural herbaceous vegetation, shrubs, and open grasslands",
    "Highway": "transportation corridors, motorways, highways, and connecting paved roads",
    "Industrial": "industrial buildings, commercial warehouses, and manufacturing facilities",
    "Pasture": "open pastures, grazing fields, and agricultural grasslands",
    "PermanentCrop": "permanent crops such as vineyards, orchards, and perennial plantations",
    "Residential": "residential urban fabric, housing developments, and settled neighborhood zones",
    "River": "natural river waterways, flowing freshwater channels, and riparian corridors",
    "SeaLake": "open water bodies including lakes, reservoirs, bays, or coastal marine waters",
}

# Rich captioning prompt templates
CAPTION_PROMPTS = [
    "Describe the land cover and major terrain features visible in this satellite image.",
    "What type of land use and geographical features are present in this remote sensing image?",
    "Summarize what this Sentinel-2 satellite image depicts.",
    "Provide a detailed description of the scene and land cover shown in this satellite observation.",
    "Identify the primary environmental and surface features in this earth observation image.",
]

# VQA query generators
def generate_vqa_pairs(class_name: str, all_classes: list[str]) -> list[tuple[str, str]]:
    """Generates positive and negative VQA questions for a given class."""
    pairs = []
    
    # 1. Positive question (Direct identification)
    q1 = f"Does this satellite image contain {class_name.lower()} or related terrain?"
    a1 = f"Yes, the scene primarily features {CLASS_DESCRIPTIONS.get(class_name, class_name)}."
    pairs.append((q1, a1))

    # 2. General land-use inquiry
    q2 = "What is the dominant land cover class observed in this satellite patch?"
    a2 = f"The dominant land cover class is {class_name}."
    pairs.append((q2, a2))

    # 3. Negative question (Ask about an absent class)
    other_classes = [c for c in all_classes if c != class_name]
    if other_classes:
        neg_class = random.choice(other_classes)
        q_neg = f"Is there any significant {neg_class.lower()} area visible in this image?"
        a_neg = f"No, this image does not show {neg_class.lower()}; it depicts {CLASS_DESCRIPTIONS.get(class_name, class_name)}."
        pairs.append((q_neg, a_neg))

    return pairs


def main():
    parser = argparse.ArgumentParser(
        description="Prepare LLaVA-format satellite training data for RSUniVLM LoRA fine-tuning."
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=400,
        help="Number of satellite images to prepare (default: 400)",
    )
    parser.add_argument(
        "--out_dir",
        type=str,
        default="./bigearthnet_llava",
        help="Output directory for images and train.json",
    )
    parser.add_argument(
        "--dataset_id",
        type=str,
        default=DEFAULT_DATASET,
        help="HuggingFace dataset ID (default: resaro/eurosat)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    img_dir = os.path.join(args.out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    print(f"Loading satellite dataset: {args.dataset_id}...")
    try:
        ds = load_dataset(args.dataset_id, split="train")
    except Exception as e:
        print(f"Failed to load split 'train', falling back to streaming mode: {e}")
        ds = load_dataset(args.dataset_id, split="train", streaming=True)

    # Resolve label class names
    if hasattr(ds, "features") and "label" in ds.features and hasattr(ds.features["label"], "names"):
        class_names = ds.features["label"].names
    else:
        class_names = list(CLASS_DESCRIPTIONS.keys())

    print(f"Loaded {len(class_names)} classes: {class_names}")

    records = []
    n_processed = 0

    print(f"Processing up to {args.n_samples} images...")
    for idx, sample in enumerate(ds):
        if n_processed >= args.n_samples:
            break

        image_raw = sample.get("image")
        if image_raw is None:
            continue

        if not isinstance(image_raw, Image.Image):
            try:
                import io
                image_raw = Image.open(io.BytesIO(image_raw))
            except Exception:
                continue

        # Get label string
        label_raw = sample.get("label", 0)
        if isinstance(label_raw, int) and label_raw < len(class_names):
            class_name = class_names[label_raw]
        else:
            class_name = str(label_raw)

        sample_id = f"sat_{n_processed:06d}"
        img_filename = f"{sample_id}.jpg"
        img_rel_path = f"images/{img_filename}"
        img_abs_path = os.path.join(img_dir, img_filename)

        # Upscale 64x64 to 224x224 for high-quality VLM feature extraction
        img_rgb = image_raw.convert("RGB")
        if img_rgb.size[0] < 224 or img_rgb.size[1] < 224:
            img_rgb = img_rgb.resize((224, 224), Image.Resampling.BICUBIC)

        img_rgb.save(img_abs_path, "JPEG", quality=95)

        # 1. Captioning conversation turn
        desc = CLASS_DESCRIPTIONS.get(class_name, class_name)
        caption_q = random.choice(CAPTION_PROMPTS)
        caption_a = f"This satellite image depicts {desc}."
        records.append({
            "id": f"{sample_id}_cap",
            "image": img_rel_path,
            "conversations": [
                {"from": "human", "value": f"<image>\n{caption_q}"},
                {"from": "gpt", "value": caption_a},
            ],
        })

        # 2. VQA conversation turn
        vqa_options = generate_vqa_pairs(class_name, class_names)
        chosen_q, chosen_a = random.choice(vqa_options)
        records.append({
            "id": f"{sample_id}_vqa",
            "image": img_rel_path,
            "conversations": [
                {"from": "human", "value": f"<image>\n{chosen_q}"},
                {"from": "gpt", "value": chosen_a},
            ],
        })

        n_processed += 1
        if n_processed % 50 == 0 or n_processed == args.n_samples:
            print(f"  Processed {n_processed}/{args.n_samples} images ({len(records)} conversation records)...")

    # Shuffle records and write output
    random.shuffle(records)
    out_json_path = os.path.join(args.out_dir, "train.json")
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"SUCCESS: Generated {len(records)} conversation samples from {n_processed} images.")
    print(f"  - Image Directory: {img_dir}")
    print(f"  - LLaVA JSON:      {out_json_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
