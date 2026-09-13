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

# The notes go through a file: a commit message with quotes inside breaks gh's command
# line when passed as an argument (v1.5.1 was announced "Released" with no release made).
$notesFile = Join-Path $env:TEMP "docling_launcher_release_notes.md"
(git log -1 --pretty=%B) -join "`n" | Set-Content -Path $notesFile -Encoding utf8
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
    gh release create $tag $exe --title "Docling Launcher $version" --notes-file $notesFile
}
if ($LASTEXITCODE -ne 0) { throw "gh failed (exit $LASTEXITCODE): the release was NOT made" }
$eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$check = gh release view $tag --json assets --jq ".assets | length"
$ErrorActionPreference = $eap
if ("$check" -ne "1") { throw "Release $tag exists but carries $check asset(s) instead of one" }
Write-Host "Released $tag with $exe"
