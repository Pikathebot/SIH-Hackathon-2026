# --------------------------------------------------------------------------
# SatQuery AI — start the local vision-language model server (llama.cpp)
#
# Serves Qwen3-VL-8B-Instruct (GGUF Q4_K_M + vision projector) on an
# OpenAI-compatible API at http://127.0.0.1:8080 for AI_ENGINE=qwen|hybrid.
#
# One-time setup (files live in tools/, which is git-ignored):
#   tools/llama.cpp/   <- llama-bXXXX-bin-win-cuda-13.x-x64.zip + cudart zip
#                         from https://github.com/ggml-org/llama.cpp/releases
#   tools/models/      <- Qwen3VL-8B-Instruct-Q4_K_M.gguf
#                         mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf
#                         from https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF
#
# VRAM budget on a 12 GB card: ~5 GB weights + ~0.7 GB mmproj + ~2.4 GB KV @16k ctx.
# --------------------------------------------------------------------------
param(
    [string]$Model = "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
    [string]$MmProj = "mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf",
    [string]$Alias = "qwen3-vl-8b",
    [int]$Port = 8080,
    [int]$Context = 16384,
    [int]$GpuLayers = 99,
    [string]$ApiKey = $env:VLM_API_KEY
)

$root = Split-Path -Parent $PSScriptRoot
$server = Join-Path $root "tools\llama.cpp\llama-server.exe"
$modelPath = Join-Path $root "tools\models\$Model"
$mmprojPath = Join-Path $root "tools\models\$MmProj"

foreach ($p in @($server, $modelPath, $mmprojPath)) {
    if (-not (Test-Path $p)) { Write-Error "Missing: $p (see setup notes at the top of this script)"; exit 1 }
}

$llamaArgs = @(
    "-m", $modelPath,
    "--mmproj", $mmprojPath,
    "--alias", $Alias,
    "--host", "127.0.0.1",
    "--port", $Port,
    "-c", $Context,
    "-ngl", $GpuLayers,
    "--jinja",
    "-np", "1"          # one slot: the backend serialises GPU work anyway
)
if ($ApiKey) { $llamaArgs += @("--api-key", $ApiKey) }

Write-Host "Starting llama-server ($Alias) on http://127.0.0.1:$Port ..."
& $server @llamaArgs
