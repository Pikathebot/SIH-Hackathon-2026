#!/bin/bash
# STEP 2 — Bash Training Script for WSL2 (Single GPU LoRA)
#
# Sized for an 8GB laptop GPU (RTX 4060): 4-bit NF4 quant on the ~1B LLM,
# LoRA rank 8, batch size 1 with grad accumulation, gradient checkpointing on.
#
# Uses the vendored RSUniVLM engine in ai_service/rsunivlm/vendor.

set -e

WORKSPACE_ROOT="/mnt/d/SIH-Hackathon-2026"
export PYTHONPATH="$WORKSPACE_ROOT/ai_service/rsunivlm/vendor:$PYTHONPATH"

CKPT_PATH="$WORKSPACE_ROOT/ai_service/rsunivlm/checkpoints/RSUniVLM"
DATA_DIR="$WORKSPACE_ROOT/LoRA_Training_Stuffs/bigearthnet_llava"
OUTPUT_DIR="$WORKSPACE_ROOT/LoRA_Training_Stuffs/checkpoints/rsunivlm-bigearthnet-lora"
PROJECT_LORA_DIR="$WORKSPACE_ROOT/ai_service/rsunivlm/checkpoints/lora_adapter"
TRAIN_SCRIPT="$WORKSPACE_ROOT/ai_service/rsunivlm/vendor/llava/train/train.py"

mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo "RSUniVLM LoRA Fine-Tuning (4-bit NF4)"
echo "============================================"
echo "Checkpoint:  $CKPT_PATH"
echo "Data:        $DATA_DIR/train.json"
echo "Output:      $OUTPUT_DIR"
echo "GPU:         $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'unknown')"
echo "============================================"
echo ""

python "$TRAIN_SCRIPT" \
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
  --fp16 True \
  --output_dir "$OUTPUT_DIR" \
  --num_train_epochs 1 \
  --per_device_train_batch_size 1 \
  --per_device_eval_batch_size 1 \
  --gradient_accumulation_steps 8 \
  --gradient_checkpointing True \
  --evaluation_strategy "no" \
  --save_strategy "steps" \
  --save_steps 50 \
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
echo "Copying to project: $PROJECT_LORA_DIR"
mkdir -p "$PROJECT_LORA_DIR"
cp -r "$OUTPUT_DIR"/* "$PROJECT_LORA_DIR"/
echo "============================================"
