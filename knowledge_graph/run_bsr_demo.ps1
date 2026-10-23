param(
    [switch]$Open
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Project .venv is missing. Run: py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.lock'
}

& $python -B -m tools.bsr_demo
if ($LASTEXITCODE -ne 0) {
    throw "BSR demo build failed with exit code $LASTEXITCODE"
}

$dashboard = Join-Path $PSScriptRoot 'output\bsr_demo\index.html'
Write-Host "BSR dashboard: $dashboard"
if ($Open) {
    Start-Process -FilePath $dashboard
}
