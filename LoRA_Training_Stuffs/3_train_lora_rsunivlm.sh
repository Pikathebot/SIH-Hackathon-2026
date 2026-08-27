#!/bin/bash
# STEP 2 — run after 2_prepare_llava_data.py has produced train.json + images/
#
# Sized for an 8GB laptop GPU (RTX 4060): 4-bit NF4 quant on the ~1B LLM,
# LoRA rank 8, batch size 1 with grad accumulation, gradient checkpointing on.
# No DeepSpeed needed for single-GPU LoRA — running train.py directly.
#
# RUNS IN WSL2 (with NVIDIA CUDA passthrough) from inside the cloned RSUniVLM repo.
#
# BEFORE RUNNING:
#   1. Download the RSUniVLM checkpoint from the Google Drive link in the repo README
#      (https://github.com/xuliu-cyber/RSUniVLM -> Demo section) and set CKPT_PATH below.
#   2. Set DATA_DIR to the --out_dir you passed to 2_prepare_llava_data.py.
#      If you prepared data on Windows, use the WSL mount path (e.g., /mnt/d/...).
#   3. From inside the cloned RSUniVLM repo root: `pip install -e ".[train]"`
#      then `pip install bitsandbytes --upgrade` (0.41.0 pinned in pyproject.toml is old).
#   4. Handle deepspeed: `pip install deepspeed` OR patch the import (see below).

set -e

# ============================================================================
#  EDIT THESE PATHS
# ============================================================================

# Path to the downloaded RSUniVLM checkpoint (the folder containing config.json,
# model safetensors, tokenizer files, etc.)
CKPT_PATH="/path/to/downloaded_rsunivlm_checkpoint"   # <-- EDIT THIS

# Path to the data dir created by 2_prepare_llava_data.py
# Use WSL mount paths if data was prepared on Windows:
#   e.g., /mnt/d/SIH-Hackathon-2026/LoRA_Training_Stuffs/bigearthnet_llava
DATA_DIR="./bigearthnet_llava"                         # <-- EDIT THIS

# Where to save the LoRA adapter output
# For integration with the SIH project, copy this to:
#   D:\SIH-Hackathon-2026\ai_service\rsunivlm\checkpoints\lora_adapter\
OUTPUT_DIR="./checkpoints/rsunivlm-bigearthnet-lora"

# ============================================================================

# Verify paths exist
if [ ! -d "$CKPT_PATH" ]; then
    echo "ERROR: CKPT_PATH does not exist: $CKPT_PATH"
    echo "Download the checkpoint from the RSUniVLM repo README first."
    exit 1
fi

if [ ! -f "$DATA_DIR/train.json" ]; then
    echo "ERROR: train.json not found at $DATA_DIR/train.json"
    echo "Run 2_prepare_llava_data.py first."
    exit 1
fi

echo "============================================"
echo "RSUniVLM LoRA Fine-Tuning (4-bit NF4)"
echo "============================================"
echo "Checkpoint:  $CKPT_PATH"
echo "Data:        $DATA_DIR/train.json"
echo "Output:      $OUTPUT_DIR"
echo "GPU:         $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'unknown')"
echo "============================================"
echo ""

python llava/train/train.py \
  --model_name_or_path "$CKPT_PATH" \
  --version qwen_2 \
  --data_path "$DATA_DIR/train.json" \
  --image_folder "$DATA_DIR" \
  --lora_enable True \
  --lora_r 8 \
  --lora_alpha 16 \
  --lora_dropout 0.05 \
  --bits 4 \
  --double_quant True \
  --quant_type nf4 \
  --bf16 True \
  --output_dir "$OUTPUT_DIR" \
  --num_train_epochs 1 \
  --per_device_train_batch_size 1 \
  --per_device_eval_batch_size 1 \
  --gradient_accumulation_steps 8 \
  --gradient_checkpointing True \
  --evaluation_strategy "no" \
  --save_strategy "steps" \
  --save_steps 100 \
  --save_total_limit 1 \
  --learning_rate 2e-4 \
  --weight_decay 0.0 \
  --warmup_ratio 0.03 \
  --lr_scheduler_type "cosine" \
  --logging_steps 1 \
  --model_max_length 1024 \
  --dataloader_num_workers 2 \
  --report_to none \
  --attn_implementation sdpa \
  --lazy_preprocess True

echo ""
echo "============================================"
echo "LoRA adapter saved to: $OUTPUT_DIR"
echo ""
echo "To integrate with SIH project, copy the adapter:"
echo "  cp -r $OUTPUT_DIR/* /mnt/d/SIH-Hackathon-2026/ai_service/rsunivlm/checkpoints/lora_adapter/"
echo ""
echo "Keep this checkpoint dir + train.json + your logged loss curve —"
echo "you'll want the hyperparameters and a loss/before-after example for the feasibility slide."
echo "============================================"
