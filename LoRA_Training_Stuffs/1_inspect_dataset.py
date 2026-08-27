"""
STEP 0 — run this FIRST, before anything else.

Confirms the actual field names in the BigEarthNet.txt HuggingFace dataset
before we build the LLaVA-format training JSON.  This is the open action
item — don't skip it, the field names determine how
2_prepare_llava_data.py needs to parse each sample.

Prerequisites:
    pip install datasets pillow
    huggingface-cli login          # BigEarthNet.txt may be gated

Usage:
    python 1_inspect_dataset.py
"""

import sys

try:
    from datasets import load_dataset
except ImportError:
    print("ERROR: `datasets` package not installed.")
    print("  pip install datasets")
    sys.exit(1)

# ---------- Dataset candidates (try in order) ----------
DATASET_IDS = [
    "BIFOLD-BigEarthNetv2-0/BigEarthNet.txt",  # Image-text version (VQA/captions)
]

NUM_SAMPLES = 3


def try_load(dataset_id: str):
    """Attempt to load a dataset in streaming mode, return iterator or None."""
    print(f"\nTrying dataset: {dataset_id}")
    try:
        ds = load_dataset(dataset_id, split="train", streaming=True)
        return ds
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "authentication" in error_msg.lower() or "gated" in error_msg.lower():
            print(f"  AUTH ERROR: Dataset requires authentication.")
            print(f"  Run: huggingface-cli login")
            print(f"  Then request access at: https://huggingface.co/datasets/{dataset_id}")
        elif "404" in error_msg or "not found" in error_msg.lower():
            print(f"  NOT FOUND: Dataset ID '{dataset_id}' does not exist.")
        else:
            print(f"  FAILED: {error_msg[:200]}")
        return None


def inspect_sample(sample: dict, index: int):
    """Pretty-print a single sample's field names, types, and truncated values."""
    print(f"\n--- Sample {index} ---")
    for key, value in sample.items():
        type_name = type(value).__name__

        # Special handling for PIL images
        if hasattr(value, "size") and hasattr(value, "mode"):
            print(f"  {key!r}: type=PIL.Image  mode={value.mode}  size={value.size}")
        elif isinstance(value, (list, tuple)):
            print(f"  {key!r}: type={type_name}  len={len(value)}  value={repr(value)[:150]}")
        elif isinstance(value, dict):
            print(f"  {key!r}: type=dict  keys={list(value.keys())}")
        elif isinstance(value, bytes):
            print(f"  {key!r}: type=bytes  len={len(value)}")
        else:
            value_repr = repr(value)
            if len(value_repr) > 200:
                value_repr = value_repr[:200] + "...(truncated)"
            print(f"  {key!r}: type={type_name}  value={value_repr}")


def print_feature_info(ds):
    """Print the dataset's declared feature schema if available."""
    try:
        features = ds.features
        if features:
            print("\n--- Dataset Feature Schema ---")
            for name, feat in features.items():
                print(f"  {name}: {feat}")
    except Exception:
        print("\n  (Feature schema not available in streaming mode)")


def main():
    ds = None
    used_id = None

    for dataset_id in DATASET_IDS:
        ds = try_load(dataset_id)
        if ds is not None:
            used_id = dataset_id
            break

    if ds is None:
        print("\n" + "=" * 60)
        print("FAILED: Could not load any dataset variant.")
        print("Check your HuggingFace authentication and network connection.")
        print("=" * 60)
        sys.exit(1)

    print(f"\nSUCCESS: Loaded '{used_id}'")

    # Print feature schema
    print_feature_info(ds)

    # Print sample data
    it = iter(ds)
    print("\n" + "=" * 60)
    print(f"FIRST {NUM_SAMPLES} SAMPLES — inspect field names and value shapes below")
    print("=" * 60)

    all_keys = set()
    for i in range(NUM_SAMPLES):
        try:
            sample = next(it)
            inspect_sample(sample, i)
            all_keys.update(sample.keys())
        except StopIteration:
            print(f"\n  Dataset exhausted after {i} samples.")
            break

    # Print summary
    print("\n" + "=" * 60)
    print("FIELD NAMES FOUND:")
    for key in sorted(all_keys):
        print(f"  - {key}")

    # Detect schema type and give advice
    print("\n" + "=" * 60)
    if "input" in all_keys and "output" in all_keys and "type" in all_keys:
        print("SCHEMA: BigEarthNet.txt (image-text version)")
        print("  This dataset already has captions and VQA pairs!")
        print("  Script 2 will use the 'input'/'output'/'type' fields directly.")
    elif any(k.startswith("B0") or k.startswith("B1") or k == "s2_image" for k in all_keys):
        print("SCHEMA: BigEarthNet v2 (band-level classification version)")
        print("  Will need to composite RGB from bands and synthesize captions from labels.")
    else:
        print("SCHEMA: Unknown — check the field names above and update")
        print("  2_prepare_llava_data.py accordingly.")

    print("\nACTION: Copy the field names printed above into")
    print("  2_prepare_llava_data.py where marked '# <-- CONFIRM FIELD NAME'")
    print("  Then run:  python 2_prepare_llava_data.py --n_samples 400 --out_dir ./bigearthnet_llava")
    print("=" * 60)


if __name__ == "__main__":
    main()
