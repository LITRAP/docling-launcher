param(
    [switch]$SkipBuild
)

# Publishes the current version as a GitHub release the launcher can update itself from:
#   1. builds dist\DoclingLauncher.exe (unless -SkipBuild),
#   2. tags v<version> (from constants.APP_VERSION) and pushes,
#   3. creates the release with the exe attached and the last commit message as notes.
# The launcher checks releases/latest at start; a private repository needs the update key.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

$constants = Get-Content (Join-Path $ProjectRoot "src\docling_launcher\constants.py") -Raw
if ($constants -notmatch 'APP_VERSION = "([^"]+)"') { throw "APP_VERSION not found" }
$version = $Matches[1]
$tag = "v$version"
$exe = Join-Path $ProjectRoot "dist\DoclingLauncher.exe"

if (-not $SkipBuild) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "build_exe.ps1") -NoShortcuts
}
if (-not (Test-Path $exe)) { throw "No exe at $exe" }

$notes = (git log -1 --pretty=%B)
git tag -f $tag
git push origin master --tags
# PowerShell 5.1 turns gh's "release not found" on stderr into a terminating error under
# "Stop"; ask about existence with the error preference relaxed.
$eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$exists = $false
try { gh release view $tag --json tagName | Out-Null; if ($LASTEXITCODE -eq 0) { $exists = $true } } catch {}
$ErrorActionPreference = $eap
if ($exists) {
    gh release upload $tag $exe --clobber
} else {
    gh release create $tag $exe --title "Docling Launcher $version" --notes "$notes"
}
Write-Host "Released $tag with $exe"
