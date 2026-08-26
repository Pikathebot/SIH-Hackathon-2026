# SatQuery AI — Local Dev Starter
# Runs Backend (FastAPI :8000) and Frontend (Vite :3000)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "       SatQuery AI - Development Stack   " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "[*] Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item .env.example .env
}

# Start backend in new terminal or background
Write-Host "[1/2] Starting Backend at http://localhost:8000..." -ForegroundColor Green
$backend = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; uv run uvicorn app.main:app --app-dir backend --port 8000 --reload" -PassThru

Write-Host "[2/2] Starting Frontend at http://localhost:3000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev"

Write-Host "`nSatQuery AI is launching!" -ForegroundColor Cyan
Write-Host "  • Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "  • Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  • API Docs: http://localhost:8000/docs" -ForegroundColor White
