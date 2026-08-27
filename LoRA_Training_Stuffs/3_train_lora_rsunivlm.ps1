# 3_train_lora_rsunivlm.ps1
# STEP 2 — PowerShell Training Script for Windows (Single GPU LoRA)
#
# Sized for an 8GB laptop GPU (RTX 4060): 4-bit NF4 quant on the ~1B LLM,
# LoRA rank 8, batch size 1 with grad accumulation, gradient checkpointing on.
#
# Uses the vendored RSUniVLM engine in ai_service/rsunivlm/vendor.
# No external clone or DeepSpeed required.

$ErrorActionPreference = "Stop"

# Set script and workspace paths
$WORKSPACE_ROOT = "D:\SIH-Hackathon-2026"
$PYTHON_EXE = "$WORKSPACE_ROOT\.venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON_EXE)) {
    $PYTHON_EXE = "python"
}

# Add vendored LLaVA to PYTHONPATH
$env:PYTHONPATH = "$WORKSPACE_ROOT\ai_service\rsunivlm\vendor;$env:PYTHONPATH"

# Paths
$CKPT_PATH = "$WORKSPACE_ROOT\ai_service\rsunivlm\checkpoints\RSUniVLM"
$DATA_DIR = "$WORKSPACE_ROOT\LoRA_Training_Stuffs\bigearthnet_llava"
$OUTPUT_DIR = "$WORKSPACE_ROOT\LoRA_Training_Stuffs\checkpoints\rsunivlm-bigearthnet-txt-lora"
$PROJECT_LORA_DIR = "$WORKSPACE_ROOT\ai_service\rsunivlm\checkpoints\lora_adapter"
$TRAIN_SCRIPT = "$WORKSPACE_ROOT\ai_service\rsunivlm\vendor\llava\train\train.py"

# Verify prerequisites
if (-not (Test-Path $CKPT_PATH)) {
    Write-Error "CKPT_PATH not found at $CKPT_PATH"
    exit 1
}

if (-not (Test-Path "$DATA_DIR\train.json")) {
    Write-Error "train.json not found at $DATA_DIR\train.json`nRun 2_prepare_llava_data.py first."
    exit 1
}

New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "RSUniVLM LoRA Fine-Tuning (4-bit NF4)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Python:      $PYTHON_EXE"
Write-Host "Checkpoint:  $CKPT_PATH"
Write-Host "Data:        $DATA_DIR\train.json"
Write-Host "Output:      $OUTPUT_DIR"

try {
    $gpuInfo = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
    Write-Host "GPU:         $gpuInfo" -ForegroundColor Green
} catch {
    Write-Host "GPU:         (nvidia-smi not found)" -ForegroundColor Yellow
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Starting QLoRA training on RTX 4060..." -ForegroundColor Yellow
Write-Host ""

# Hyperparameters tailored for 8GB VRAM
$MODEL_MAX_LENGTH = 1024
$LORA_R = 8

& $PYTHON_EXE $TRAIN_SCRIPT `
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
  --fp16 True `
  --output_dir "$OUTPUT_DIR" `
  --overwrite_output_dir True `
  --num_train_epochs 1 `
  --per_device_train_batch_size 1 `
  --per_device_eval_batch_size 1 `
  --gradient_accumulation_steps 8 `
  --gradient_checkpointing True `
  --evaluation_strategy "no" `
  --save_strategy "steps" `
  --save_steps 50 `
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

if ($LASTEXITCODE -ne 0) {
    Write-Error "Training failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "LoRA adapter saved to: $OUTPUT_DIR" -ForegroundColor Green
Write-Host ""

if ((Test-Path "$OUTPUT_DIR\adapter_model.safetensors") -or (Test-Path "$OUTPUT_DIR\adapter_model.bin")) {
    Write-Host "Copying fine-tuned adapter to SatQuery AI project at:"
    Write-Host "  $PROJECT_LORA_DIR"
    New-Item -ItemType Directory -Force -Path $PROJECT_LORA_DIR | Out-Null
    Copy-Item -Recurse -Force "$OUTPUT_DIR\*" "$PROJECT_LORA_DIR\"
    Write-Host "Adapter synced to project successfully!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next step: Run the project with AI_SERVICE_MODE=real in .env to test real inference!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Green
