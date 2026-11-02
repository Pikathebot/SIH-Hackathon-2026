# SatQuery AI — one-command native dev run on Windows
#   .\start_dev.ps1            backend (:8000, --reload) + frontend (Vite :3000), and llama-server (:8080)
#                              when .env asks for the real qwen/hybrid engine and it is not already up
#   .\start_dev.ps1 -NoVlm     never start llama-server
# First-time setup: see QUICKSTART.md (creates .venv and installs requirements.lock).
param([switch]$NoVlm)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "       SatQuery AI - Development Stack   " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "[*] Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item .env.example .env
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "No .venv found. Run: uv venv --python 3.11 .venv; uv pip install -r requirements.lock (see QUICKSTART.md)"
}

# Read the few .env values that decide whether llama-server is needed
$envVars = @{}
Get-Content .env | Where-Object { $_ -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$' } | ForEach-Object {
    $envVars[$Matches[1]] = $Matches[2]
}
$mode = if ($envVars["AI_SERVICE_MODE"]) { $envVars["AI_SERVICE_MODE"] } else { "mock" }
$engine = if ($envVars["AI_ENGINE"]) { $envVars["AI_ENGINE"] } else { "hybrid" }
$needVlm = (-not $NoVlm) -and $mode -eq "real" -and ($engine -eq "qwen" -or $engine -eq "hybrid")

if ($needVlm) {
    $up = $false
    try { $up = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8080/health).StatusCode -eq 200 } catch {}
    if ($up) {
        Write-Host "[0/2] llama-server already running on :8080" -ForegroundColor Green
    } else {
        Write-Host "[0/2] Starting llama-server (Qwen3-VL) on :8080 ... close ComfyUI / LM Studio first (VRAM)" -ForegroundColor Green
        Start-Process powershell -ArgumentList "-NoExit", "-File", "`"$PSScriptRoot\scripts\start_vlm_server.ps1`""
        for ($i = 0; $i -lt 90 -and -not $up; $i++) {
            Start-Sleep -Seconds 2
            try { $up = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8080/health).StatusCode -eq 200 } catch {}
        }
        if (-not $up) { Write-Warning "llama-server is not up yet; the backend will fall back to rsunivlm if it stays down." }
    }
}

Write-Host "[1/2] Starting backend at http://localhost:8000 (mode=$mode, engine=$engine)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$PSScriptRoot'; & '$python' -m uvicorn app.main:app --app-dir backend --port 8000 --reload --reload-dir backend/app --reload-dir ai_service"

Write-Host "[2/2] Starting frontend at http://localhost:3000..." -ForegroundColor Green
$install = if (Test-Path "frontend\node_modules") { "" } else { "npm ci; " }
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; ${install}npm run dev"

Write-Host "`nSatQuery AI is launching!" -ForegroundColor Cyan
Write-Host "  - Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "  - Backend:  http://localhost:8000  (docs: /docs, health: /api/v1/health, ready: /api/v1/ready)" -ForegroundColor White
