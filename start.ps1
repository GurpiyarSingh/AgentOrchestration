# Starts Codeloom at http://127.0.0.1:8000 (UI + API + Swagger at /docs).
# Builds the web UI first when it is missing or older than its sources.
#   .\start.ps1            build if needed, then start
#   .\start.ps1 -Rebuild   force a UI rebuild
#   .\start.ps1 -Port 8080 use another port
param([switch]$Rebuild, [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { $env:Path = "$HOME\.local\bin;$env:Path" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js is required to build the UI (winget install OpenJS.NodeJS.LTS)." }

uv sync --quiet

if (-not (Test-Path "web\node_modules")) {
    Write-Host "Installing UI dependencies..." -ForegroundColor Cyan
    npm --prefix web install --no-fund --no-audit
}
$index = "web\dist\index.html"
$srcTime = (Get-ChildItem web\src, web\index.html, web\vite.config.ts -Recurse -File | Measure-Object LastWriteTime -Maximum).Maximum
if ($Rebuild -or -not (Test-Path $index) -or (Get-Item $index).LastWriteTime -lt $srcTime) {
    Write-Host "Building the UI..." -ForegroundColor Cyan
    npm --prefix web run build
}

Write-Host "`nCodeloom → http://127.0.0.1:$Port   (API docs: http://127.0.0.1:$Port/docs)`n" -ForegroundColor Green
uv run uvicorn api.main:app --host 127.0.0.1 --port $Port
