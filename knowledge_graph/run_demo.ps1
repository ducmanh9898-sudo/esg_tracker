$ErrorActionPreference = "Stop"

Write-Host "[1/2] Chay bo kiem thu..." -ForegroundColor Cyan
python -m unittest discover -s .\tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Kiem thu that bai. Dung pipeline de khong tao demo sai."
}

Write-Host "[2/2] Tao lai du lieu va mo graph..." -ForegroundColor Cyan
python .\build_demo.py
if ($LASTEXITCODE -ne 0) {
    throw "Khong tao duoc graph demo."
}

Write-Host "Hoan tat: output\graph_demo.html" -ForegroundColor Green
