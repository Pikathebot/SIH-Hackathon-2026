# 3_train_lora_rsunivlm.ps1
# STEP 2 — PowerShell alternative for Windows (no WSL needed)
#
# Sized for an 8GB laptop GPU (RTX 4060): 4-bit NF4 quant on the ~1B LLM,
# LoRA rank 8, batch size 1 with grad accumulation, gradient checkpointing on.
# No DeepSpeed needed for single-GPU LoRA — running train.py directly.
#
# IMPORTANT: Run this from inside the cloned RSUniVLM repo root directory.
#
# BEFORE RUNNING:
#   1. Download the RSUniVLM checkpoint from the Google Drive link in the repo README
#      (https://github.com/xuliu-cyber/RSUniVLM -> Demo section) and set $CKPT_PATH below.
#   2. Set $DATA_DIR to the --out_dir you passed to 2_prepare_llava_data.py.
#   3. From inside the cloned RSUniVLM repo root:
#        pip install -e ".[train]"
#        pip install bitsandbytes --upgrade
#   4. Handle deepspeed import:
#        Option A: pip install deepspeed (may need VS Build Tools on Windows)
#        Option B: Patch train.py line "import deepspeed" to:
#                  try:
#                      import deepspeed
#                  except ImportError:
#                      deepspeed = None

$ErrorActionPreference = "Stop"

# ============================================================================
#  EDIT THESE PATHS
# ============================================================================

# Path to the downloaded RSUniVLM checkpoint (the folder containing config.json,
# model safetensors, tokenizer files, etc.)
$CKPT_PATH = "D:\path\to\downloaded_rsunivlm_checkpoint"   # <-- EDIT THIS

# Path to the data dir created by 2_prepare_llava_data.py
$DATA_DIR = "D:\SIH-Hackathon-2026\LoRA_Training_Stuffs\bigearthnet_llava"   # <-- EDIT THIS

# Where to save the LoRA adapter output
$OUTPUT_DIR = ".\checkpoints\rsunivlm-bigearthnet-lora"

# Project integration path (where to copy the adapter after training)
$PROJECT_LORA_DIR = "D:\SIH-Hackathon-2026\ai_service\rsunivlm\checkpoints\lora_adapter"

# ============================================================================

# Verify paths
if (-not (Test-Path $CKPT_PATH)) {
    Write-Error "CKPT_PATH does not exist: $CKPT_PATH`nDownload the checkpoint from the RSUniVLM repo README first."
    exit 1
}

if (-not (Test-Path "$DATA_DIR\train.json")) {
    Write-Error "train.json not found at $DATA_DIR\train.json`nRun 2_prepare_llava_data.py first."
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "RSUniVLM LoRA Fine-Tuning (4-bit NF4)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Checkpoint:  $CKPT_PATH"
Write-Host "Data:        $DATA_DIR\train.json"
Write-Host "Output:      $OUTPUT_DIR"

# Show GPU info
try {
    $gpuInfo = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
    Write-Host "GPU:         $gpuInfo"
} catch {
    Write-Host "GPU:         (nvidia-smi not found)" -ForegroundColor Yellow
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# OOM safety knobs (uncomment to reduce memory):
# $MODEL_MAX_LENGTH = 512   # drop from 1024 to 512
# $LORA_R = 4               # drop from 8 to 4
$MODEL_MAX_LENGTH = 1024
$LORA_R = 8

python llava/train/train.py `
  --model_name_or_path "$CKPT_PATH" `
  --version qwen_2 `
  --data_path "$DATA_DIR\train.json" `
  --image_folder "$DATA_DIR" `
  --lora_enable True `
  --lora_r $LORA_R `
  --lora_alpha 16 `
  --lora_dropout 0.05 `
  --bits 4 `
  --double_quant True `
  --quant_type nf4 `
  --bf16 True `
  --output_dir "$OUTPUT_DIR" `
  --num_train_epochs 1 `
  --per_device_train_batch_size 1 `
  --per_device_eval_batch_size 1 `
  --gradient_accumulation_steps 8 `
  --gradient_checkpointing True `
  --evaluation_strategy "no" `
  --save_strategy "steps" `
  --save_steps 100 `
  --save_total_limit 1 `
  --learning_rate 2e-4 `
  --weight_decay 0.0 `
  --warmup_ratio 0.03 `
  --lr_scheduler_type "cosine" `
  --logging_steps 1 `
  --model_max_length $MODEL_MAX_LENGTH `
  --dataloader_num_workers 2 `
  --report_to none `
  --attn_implementation sdpa `
  --lazy_preprocess True

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "LoRA adapter saved to: $OUTPUT_DIR" -ForegroundColor Green
Write-Host ""

# Offer to copy to project integration path
if (Test-Path $OUTPUT_DIR) {
    Write-Host "To integrate with SIH project, run:"
    Write-Host "  Copy-Item -Recurse -Force '$OUTPUT_DIR\*' '$PROJECT_LORA_DIR\'"
    Write-Host ""

    $confirm = Read-Host "Copy adapter to project now? (y/N)"
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        New-Item -ItemType Directory -Force -Path $PROJECT_LORA_DIR | Out-Null
        Copy-Item -Recurse -Force "$OUTPUT_DIR\*" "$PROJECT_LORA_DIR\"
        Write-Host "Copied to $PROJECT_LORA_DIR" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Keep this checkpoint dir + train.json + your logged loss curve —"
Write-Host "you'll want the hyperparameters and a loss/before-after example for the feasibility slide."
Write-Host "============================================" -ForegroundColor Green
