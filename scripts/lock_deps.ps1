# Regenerate the Python dependency locks from the versions that are installed (and tested) in .venv.
#
#   requirements.lock          full GPU stack (backend + RSUniVLM/Qwen + torch cu128)
#   backend/requirements.lock  backend + mock AI only (no torch), for the slim image / CI
#
# Workflow: change a requirements*.txt -> `uv pip install -r ...` into .venv -> run the tests
# -> run this script. The locks are cross-platform (uv --universal) but every package that is
# installed in .venv is held to exactly that version, so a lock never drifts from what was tested.
#
# transformers==4.46.0 is yanked on PyPI only for Python 3.8; it is the version RSUniVLM needs.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "satquery-lock"
New-Item -ItemType Directory -Force $tmp | Out-Null
$freeze = Join-Path $tmp "installed.txt"
$torchIn = Join-Path $tmp "torch.in"

uv pip freeze --python $py | Out-File -Encoding utf8 $freeze
"torch`ntorchvision" | Out-File -Encoding utf8 $torchIn

$common = @("--universal", "--python-version", "3.11", "-c", $freeze, "--no-annotate", "--quiet")

Push-Location $root
try {
    uv pip compile requirements.txt $torchIn @common `
        --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match `
        --custom-compile-command "scripts/lock_deps.ps1" -o requirements.lock
    uv pip compile backend/requirements.txt @common `
        --custom-compile-command "scripts/lock_deps.ps1" -o backend/requirements.lock
    Write-Host "Wrote requirements.lock and backend/requirements.lock"
} finally {
    Pop-Location
}
