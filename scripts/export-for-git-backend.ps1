# Export python_api contents for copy-paste into HO-backend Git repo (repo root = this folder)
$ErrorActionPreference = "Stop"

$apiRoot = Split-Path $PSScriptRoot -Parent
$projectRoot = Split-Path $apiRoot -Parent
$exportDir = Join-Path $projectRoot "HO-backend-copy"

$includeNames = @(
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
    ".gitignore",
    "create_admin.py",
    "RENDER_DEPLOY.md",
    "DEPLOY_WITHOUT_GIT.md"
)

$excludeDirNames = @("venv", ".venv", "env", "__pycache__", ".git", "node_modules")
$excludeFileNames = @("app.zip", ".env", ".env.local", ".env.production", ".env.development")

function Should-SkipPath([string]$name, [bool]$isDir) {
    if ($excludeFileNames -contains $name) { return $true }
    if ($isDir -and ($excludeDirNames -contains $name)) { return $true }
    if (-not $isDir -and $name -match '\.pyc$') { return $true }
    return $false
}

function Copy-TreeFiltered([string]$src, [string]$dest) {
    if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
    Get-ChildItem -LiteralPath $src -Force | ForEach-Object {
        if (Should-SkipPath $_.Name $_.PSIsContainer) { return }
        $target = Join-Path $dest $_.Name
        if ($_.PSIsContainer) {
            Copy-TreeFiltered $_.FullName $target
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

Write-Host "Exporting backend for Git copy-paste..."
Write-Host "  Source: $apiRoot"
Write-Host "  Target: $exportDir"
Write-Host ""

if (Test-Path $exportDir) { Remove-Item $exportDir -Recurse -Force }
New-Item -ItemType Directory -Path $exportDir -Force | Out-Null

foreach ($name in $includeNames) {
    $src = Join-Path $apiRoot $name
    if (-not (Test-Path $src)) { continue }
    $dest = Join-Path $exportDir $name
    if ((Get-Item $src).PSIsContainer) {
        Copy-TreeFiltered $src $dest
    } else {
        Copy-Item -LiteralPath $src -Destination $dest -Force
    }
}

# Instructions file (always overwrite)
$readme = @"
# HO-backend — copy into your Git repo

This folder mirrors what the **HO-backend** Git repo root must contain.
Do not upload the ``HO-backend-copy`` folder itself — upload **everything inside it**.

## Copy-paste steps

1. Open your backend Git repo on your PC (e.g. ``HO-backend`` clone).
2. **Backup** the repo if needed.
3. Select **all files and folders inside** ``HO-backend-copy`` (not the parent folder):
   - ``app/``
   - ``scripts/``
   - ``run_render.py``
   - ``requirements.txt``
   - ``render.yaml``
   - etc.
4. Paste into the **root** of the Git repo (replace when asked).
5. Do **not** copy: ``venv/``, ``.env``, ``app.zip``.

## Git push

``````bash
cd path/to/HO-backend
git status
git add .
git commit -m "Update backend: featured/new property sort order"
git push origin main
``````

Render will auto-deploy after push (if connected).

## Repo root must look like

``````
HO-backend/
  app/
  run_render.py
  requirements.txt
  render.yaml
  ...
``````

**Not** nested as ``HO-backend/python_api/app/``.

Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
"@
Set-Content -Path (Join-Path $exportDir "README-GIT-COPY.md") -Value $readme -Encoding UTF8

$fileCount = (Get-ChildItem $exportDir -Recurse -File).Count
$sizeMB = [math]::Round((Get-ChildItem $exportDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB, 2)

Write-Host "Done."
Write-Host "  Files: $fileCount"
Write-Host "  Size:  $sizeMB MB"
Write-Host ""
Write-Host "Open this folder and copy ALL contents into your Git backend repo root:"
Write-Host "  $exportDir"
Write-Host ""
