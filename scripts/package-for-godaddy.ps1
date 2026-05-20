# Package Python API for GoDaddy / server upload (excludes venv and dev files)
$ErrorActionPreference = "Stop"

$apiRoot = Split-Path $PSScriptRoot -Parent
$staging = Join-Path $env:TEMP "homeandown-api-staging-$(Get-Date -Format 'yyyyMMddHHmmss')"
$zipPath = Join-Path $apiRoot "app.zip"

$include = @(
    "app",
    "scripts",
    "requirements.txt",
    "requirements_render.txt",
    "run_render.py",
    "run_server.py",
    "server.py",
    "passenger_wsgi.py",
    "gunicorn.conf.py",
    "render.yaml",
    ".python-version",
    ".htaccess",
    "DEPLOY_WITHOUT_GIT.md",
    "RENDER_DEPLOY.md"
)

Write-Host "Packaging backend from: $apiRoot"

if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null

foreach ($item in $include) {
    $src = Join-Path $apiRoot $item
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $staging $item) -Recurse -Force
    }
}

# Strip caches from copied tree
Get-ChildItem -Path $staging -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
Get-ChildItem -Path $staging -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Force }

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force
Remove-Item $staging -Recurse -Force

$file = Get-Item $zipPath
$sizeMB = [math]::Round($file.Length / 1MB, 2)

Write-Host ""
Write-Host "Backend package ready:"
Write-Host "  File: $zipPath"
Write-Host "  Size: $sizeMB MB"
Write-Host "  Upload to server ~/api/ and extract, then: pip install -r requirements.txt && restart API"
Write-Host ""
