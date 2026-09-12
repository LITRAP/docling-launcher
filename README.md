# Docling Launcher

Windows Tkinter desktop launcher for batch `docling convert` runs.

## Input Selection

By default, the launcher converts every supported file in the input folder and its
subfolders. Clear **Convert every supported file in this folder** to enable
**Select Files...**, then choose one or more supported files from that input folder.
Only those chosen files are converted; the configured output mode still applies.

## Build

From `E:\DoclingLauncherApp`:

```powershell
.\build_exe.ps1
```

The script removes `build` and `dist`, then creates a one-file windowed executable at:

```text
E:\DoclingLauncherApp\dist\DoclingLauncher.exe
```

The executable automatically looks for Docling at `.venv\Scripts\docling.exe`, next to the project, next to the executable, or on `PATH`.
