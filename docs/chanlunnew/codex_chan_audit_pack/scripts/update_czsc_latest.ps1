[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12",
    [string]$VenvPath = ".venv-czsc-rc8",
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Run-Step {
    param(
        [string]$Title,
        [scriptblock]$Command
    )

    Write-Host "`n== $Title ==" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/"
}

$env:UV_CACHE_DIR = Join-Path $Root ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Root ".uv-python"
$VenvPython = Join-Path $Root "$VenvPath\Scripts\python.exe"

Write-Host "`n== Create Python $PythonVersion environment ==" -ForegroundColor Cyan
uv venv $VenvPath --python $PythonVersion --clear
if ($LASTEXITCODE -ne 0) {
    Write-Host "uv venv failed; falling back to the managed Python interpreter." -ForegroundColor Yellow
    $ManagedPython = uv python find $PythonVersion
    if ($LASTEXITCODE -ne 0 -or -not $ManagedPython) {
        throw "Cannot find a Python $PythonVersion interpreter"
    }
    & $ManagedPython -m venv --clear --without-pip $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Fallback venv creation failed with exit code $LASTEXITCODE"
    }
}

Run-Step "Install czsc 1.0.0rc8" {
    uv pip install --python $VenvPython --upgrade --prerelease=allow "czsc==1.0.0rc8"
}

Run-Step "Print installed versions" {
    & $VenvPython -c "import sys, czsc, importlib.metadata as m; print('python:', sys.version); print('czsc:', m.version('czsc')); print('czsc file:', czsc.__file__)"
}

if (-not $SkipVerify) {
    Run-Step "Run runtime verification" {
        & $VenvPython scripts/verify_runtime_with_czsc.py
    }
}

Write-Host "`nczsc 1.0.0rc8 environment is ready: $VenvPython" -ForegroundColor Green
