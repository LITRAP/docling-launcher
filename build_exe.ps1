param(
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

Set-Location $ProjectRoot

if (-not $SkipClean) {
    Remove-Item -LiteralPath (Join-Path $ProjectRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $ProjectRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "DoclingLauncher" `
    --paths (Join-Path $ProjectRoot "src") `
    (Join-Path $ProjectRoot "main.py")

Write-Host "Built executable: $(Join-Path $ProjectRoot 'dist\DoclingLauncher.exe')"
