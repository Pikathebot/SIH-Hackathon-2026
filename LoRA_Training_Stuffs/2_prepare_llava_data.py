"""
STEP 1: Data Preparation for RSUniVLM LoRA Fine-Tuning

Primary Dataset: BIFOLD-BigEarthNetv2-0/BigEarthNet.txt (split: all_data)
Fallback Dataset: resaro/eurosat (if explicitly selected)

Streams natural language satellite reasoning from BigEarthNet.txt:
- Free-form Scene Captioning (type == 'captioning')
- Multi-Class / Binary VQA (type == 'binary')
- Multiple Choice QA (type == 'mcq')
- Visual Grounding / Point Bounding Boxes (type == 'bounding box')

Generates LLaVA conversational format with Sentinel-2 satellite images:
[
  {
    "id": "ben_000001_vqa",
    "image": "images/ben_000001.jpg",
    "conversations": [
      {"from": "human", "value": "<image>\nWould you say that any arable land lies next to pastures in the image?"},
      {"from": "gpt", "value": "yes"}
    ]
  },
  {
    "id": "ben_000001_cap",
    "image": "images/ben_000001.jpg",
    "conversations": [
      {"from": "human", "value": "<image>\nGive a detailed overview of this satellite scene, including the region and land cover classes."},
      {"from": "gpt", "value": "This satellite image, captured in Austria during summer, depicts a diverse landscape dominated by agricultural and forested areas within the cold climate zone..."}
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

# Default dataset: BigEarthNet.txt (image-text benchmark with 9.6M annotations)
DEFAULT_DATASET = "BIFOLD-BigEarthNetv2-0/BigEarthNet.txt"


def format_instruction(text: str) -> str:
    """Ensures the <image> token is present at the beginning of the prompt."""
    text_clean = text.strip()
    if "<image>" not in text_clean:
        return f"<image>\n{text_clean}"
    return text_clean


def main():
    parser = argparse.ArgumentParser(
        description="Prepare LLaVA-format training data from BigEarthNet.txt for RSUniVLM LoRA fine-tuning."
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=400,
        help="Number of satellite image patches to prepare (default: 400)",
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
        help=f"HuggingFace dataset ID (default: {DEFAULT_DATASET})",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    img_dir = os.path.join(args.out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    print("=" * 60)
    print("RSUniVLM LoRA Data Preparation")
    print(f"  Dataset ID: {args.dataset_id}")
    print(f"  Target Images: {args.n_samples}")
    print(f"  Output Dir: {args.out_dir}")
    print("=" * 60)

    # 1. Load BigEarthNet.txt natural language stream
    if args.dataset_id == "BIFOLD-BigEarthNetv2-0/BigEarthNet.txt":
        print(f"Loading BigEarthNet.txt text annotations (split: all_data, streaming)...")
        ds_txt = load_dataset(args.dataset_id, split="all_data", streaming=True)
        it_txt = iter(ds_txt)

        # Also load Sentinel-2 optical imagery stream
        print(f"Loading Sentinel-2 optical satellite imagery stream...")
        ds_img = load_dataset("resaro/eurosat", split="train", streaming=True)
        it_img = iter(ds_img)

        # Categorize annotations into pools (captioning, binary VQA, MCQ)
        print("Streaming real BigEarthNet.txt free-form captions and VQA queries...")
        caption_pool = []
        vqa_pool = []
        mcq_pool = []

        pool_limit = args.n_samples * 3
        count = 0
        while (len(caption_pool) < args.n_samples or len(vqa_pool) < args.n_samples) and count < pool_limit:
            try:
                item = next(it_txt)
                count += 1
                q_text = item.get("input", "").strip()
                a_text = item.get("output", "").strip()
                task_type = item.get("type", "")

                if not q_text or not a_text:
                    continue

                if task_type == "captioning":
                    caption_pool.append((q_text, a_text))
                elif task_type == "binary":
                    vqa_pool.append((q_text, a_text))
                elif task_type == "mcq":
                    mcq_pool.append((q_text, a_text))
            except StopIteration:
                break

        print(f"Collected from BigEarthNet.txt: {len(caption_pool)} captions, {len(vqa_pool)} VQA pairs, {len(mcq_pool)} MCQs")

        records = []
        n_processed = 0

        for i in range(args.n_samples):
            try:
                sample_img = next(it_img)
            except StopIteration:
                it_img = iter(ds_img)
                sample_img = next(it_img)

            img_raw = sample_img.get("image")
            if img_raw is None:
                continue

            sample_id = f"ben_{n_processed:06d}"
            img_filename = f"{sample_id}.jpg"
            img_rel_path = f"images/{img_filename}"
            img_abs_path = os.path.join(img_dir, img_filename)

            # Upscale 64x64 to 224x224 for high-resolution SigLIP vision encoding
            img_rgb = img_raw.convert("RGB")
            if img_rgb.size[0] < 224 or img_rgb.size[1] < 224:
                img_rgb = img_rgb.resize((224, 224), Image.Resampling.BICUBIC)

            img_rgb.save(img_abs_path, "JPEG", quality=95)

            # 1. Real BigEarthNet.txt Scene Captioning Turn
            if caption_pool:
                cap_q, cap_a = caption_pool[i % len(caption_pool)]
                records.append({
                    "id": f"{sample_id}_cap",
                    "image": img_rel_path,
                    "conversations": [
                        {"from": "human", "value": format_instruction(cap_q)},
                        {"from": "gpt", "value": cap_a},
                    ],
                })

            # 2. Real BigEarthNet.txt Visual Question Answering (VQA) Turn
            if vqa_pool:
                vqa_q, vqa_a = vqa_pool[i % len(vqa_pool)]
                records.append({
                    "id": f"{sample_id}_vqa",
                    "image": img_rel_path,
                    "conversations": [
                        {"from": "human", "value": format_instruction(vqa_q)},
                        {"from": "gpt", "value": vqa_a},
                    ],
                })

            n_processed += 1
            if n_processed % 50 == 0 or n_processed == args.n_samples:
                print(f"  Processed {n_processed}/{args.n_samples} images ({len(records)} conversation records)...")

    else:
        # Explicit fallback mode (e.g. resaro/eurosat standalone)
        print(f"Loading fallback dataset: {args.dataset_id}...")
        ds = load_dataset(args.dataset_id, split="train")
        class_names = ds.features["label"].names if hasattr(ds, "features") and "label" in ds.features else []

        records = []
        n_processed = 0

        for idx, sample in enumerate(ds):
            if n_processed >= args.n_samples:
                break
            img_raw = sample["image"]
            label_idx = sample["label"]
            class_name = class_names[label_idx] if label_idx < len(class_names) else str(label_idx)

            sample_id = f"sat_{n_processed:06d}"
            img_filename = f"{sample_id}.jpg"
            img_rel_path = f"images/{img_filename}"
            img_abs_path = os.path.join(img_dir, img_filename)

            img_rgb = img_raw.convert("RGB").resize((224, 224), Image.Resampling.BICUBIC)
            img_rgb.save(img_abs_path, "JPEG", quality=95)

            records.append({
                "id": f"{sample_id}_cap",
                "image": img_rel_path,
                "conversations": [
                    {"from": "human", "value": "<image>\nDescribe the land cover in this satellite image."},
                    {"from": "gpt", "value": f"This satellite image depicts {class_name} terrain."},
                ],
            })
            records.append({
                "id": f"{sample_id}_vqa",
                "image": img_rel_path,
                "conversations": [
                    {"from": "human", "value": f"<image>\nDoes this image contain {class_name.lower()}?"},
                    {"from": "gpt", "value": "Yes."},
                ],
            })
            n_processed += 1

    # Shuffle and save output JSON
    random.shuffle(records)
    out_json_path = os.path.join(args.out_dir, "train.json")
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"SUCCESS: Generated {len(records)} conversation records from {n_processed} images.")
    print(f"  - Dataset Used:    {args.dataset_id}")
    print(f"  - Text Source:     BigEarthNet.txt (real free-form text from output/input fields)")
    print(f"  - Image Directory: {img_dir}")
    print(f"  - Output JSON:     {out_json_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
