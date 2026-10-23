param(
    [string]$RunDir = "output/bsr_esg_bctc_temporal_final_20261023",
    [int]$Port = 8765
)

$repoRoot = $PSScriptRoot
$entry = Join-Path $repoRoot (Join-Path $RunDir "index.html")
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    throw "Không tìm thấy dashboard: $entry. Hãy chạy Extract → Graph trước."
}

$python = Join-Path $repoRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = "python"
}

$urlPath = ($RunDir -replace '\\','/').Trim('/')
$url = "http://127.0.0.1:$Port/$urlPath/index.html"
Write-Host "Dashboard BSR: $url"
Write-Host "Dừng máy chủ bằng Ctrl+C."
& $python -m http.server $Port --bind 127.0.0.1 --directory $repoRoot
