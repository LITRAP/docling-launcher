param(
    [switch]$SkipClean,
    [switch]$NoShortcuts
)

# Builds ONE exe, dist\DoclingLauncher.exe, with its own icon, and puts a shortcut to it on
# the Desktop and in the Start menu (from where it can be pinned to the taskbar).
# The exe is built from Docling's own environment (.venv), so it always matches it.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$Icon = Join-Path $ProjectRoot "src\docling_launcher\assets\docling_launcher.ico"
$Assets = Join-Path $ProjectRoot "src\docling_launcher\assets"
$Exe = Join-Path $ProjectRoot "dist\DoclingLauncher.exe"

Set-Location $ProjectRoot
$BuildStarted = Get-Date

if (-not $SkipClean) {
    Remove-Item -LiteralPath (Join-Path $ProjectRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $ProjectRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue
}

# The obsolete 'typing' backport (a dependency of resemblyzer, the speaker-separation part
# of Docling's video mode) shadows the standard library and PyInstaller refuses to build with
# it present. It does nothing on a modern Python, so it is removed before every build.
# (pip prints a harmless warning when it is already gone; PowerShell 5.1 would turn that
# stderr line into a terminating error under "Stop", so it runs under "Continue".)
$eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
& $Python -m pip uninstall -y -q typing | Out-Null
# resemblyzer (speaker separation) imports pkg_resources, which setuptools 80+ no longer
# ships; without this pin "who said what" silently switches itself off.
& $Python -m pip install -q "setuptools<80" "transformers<5.8" | Out-Null
# "Who said what" (best): the voice features of assets/speakers_tool.py come from
# kaldi-native-fbank (one small wheel, no dependencies); the two ONNX models are downloaded
# by the launcher's model update, not baked into the exe.
& $Python -m pip install -q kaldi-native-fbank | Out-Null
# OCR runs on the card through onnxruntime-gpu; a stray processor edition beside it breaks OCR.
& $Python -m pip uninstall -y -q onnxruntime | Out-Null
$ErrorActionPreference = $eap

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "DoclingLauncher" `
    --icon $Icon `
    --add-data "$Assets;docling_launcher\assets" `
    --collect-all sv_ttk `
    --paths (Join-Path $ProjectRoot "src") `
    (Join-Path $ProjectRoot "main.py")

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit code $LASTEXITCODE). Is the launcher still open? Close it and build again." }
if (-not (Test-Path $Exe)) { throw "Build produced no exe at $Exe" }
if ((Get-Item $Exe).LastWriteTime -lt $BuildStarted) { throw "The exe at $Exe is older than this build - it was not replaced." }
Write-Host "Built executable: $Exe"

if (-not $NoShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    $targets = @(
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "Docling Launcher.lnk"),
        (Join-Path ([Environment]::GetFolderPath("Programs")) "Docling Launcher.lnk")
    )
    foreach ($path in $targets) {
        $shortcut = $shell.CreateShortcut($path)
        $shortcut.TargetPath = $Exe
        $shortcut.WorkingDirectory = Split-Path -Parent $Exe
        $shortcut.IconLocation = "$Exe,0"
        $shortcut.Description = "Batch document conversion with Docling"
        $shortcut.Save()
        Write-Host "Shortcut: $path"
    }
    Write-Host "To pin: right-click the Start menu entry 'Docling Launcher' -> Pin to taskbar."
}
