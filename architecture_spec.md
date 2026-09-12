# Docling Launcher Architecture Spec

## Purpose
Build a Windows desktop GUI application that acts as a batch launcher for Docling conversions. The user should be able to select input and output folders, choose conversion mode, select output formats, choose OCR settings, toggle plugin behavior, check environment support, and run batch conversions with clear logs and visible status.

## Design goals
The app must be simple enough for non-technical users while still exposing advanced options for OCR and output behavior. The interface should make the current command preview visible so users can understand what will run before starting conversion. The app must also save settings locally between sessions.

## Platform and packaging
Target platform: Windows desktop. Use Python with Tkinter for the GUI, and package the app with PyInstaller as a single-file GUI executable using a one-file, windowed build. The build process should assume a clean rebuild workflow where `build` and `dist` are deleted before packaging.

## Main screen layout
Use a vertical, sectioned layout with clearly labeled groups. The app window should open at a medium-large size, be resizable, and have a minimum size that prevents the controls from collapsing.

## Header area
The header should contain the app title and a small top-right cluster for help and tooltips. Include a “How to Use” button and a “Show tooltips” checkbox.

## Updates section
Create an “Updates” group near the top with three actions: “How to Use”, “Check Docling Updates”, and “Check Extensions / Add-ins Updates”.

## Input/output section
Provide two folder selectors: Input folder and Output folder. Each selector should include a label, an editable text field, and a Browse button.

## Conversion mode behavior
Provide three mutually exclusive radio-button modes: mirror input folder structure into output folder, save converted files beside the original files, and save all converted files into one output folder.

## Output formats section
Allow multiple output formats to be selected at once. Recommended formats: Markdown, JSON, HTML, Text, DocLang XML, Doctags, WebVTT, and DCLX.

## OCR and plugins section
Provide OCR engine selection as a dropdown and a checkbox for “Allow external plugins.”

## Portable Tesseract section
Add a separate “Portable Tesseract” section for users who want to point the app to a bundled Tesseract installation on USB or in a portable folder.

## Extension status section
Show a live status panel for key dependencies: RapidOCR, EasyOCR, Tesseract, and OnnxTR.

## Run section
The run section should include a “Run Batch Conversion” button, a “Check Extensions” button, an “Exit” button, a read-only command preview field, and a checkbox for “Run as Administrator.”

## Log section
The bottom of the app should contain a scrollable log panel that shows discovery of input files, each file conversion target, subprocess output, exit codes, errors, and warnings.

## Settings persistence
The app should save input folder, output folder, OCR engine, external plugin toggle, run as admin toggle, output formats, portable Tesseract toggle, portable Tesseract path, conversion mode, and show tooltips toggle.

## Tooltip behavior
Tooltips should be available for nearly every control. The user should be able to turn them on or off with a checkbox.

## Tutorial dialog
Create a “How to Use” dialog that opens as a separate scrollable window with a numbered step-by-step guide.

## Conversion workflow
When the user clicks Run Batch Conversion, validate the input folder, validate output folder if needed, validate selected formats, collect supported input files, build destination paths, create directories, run `docling convert` for each file, append progress and errors to the log, and finish with a completion message.

## Command preview rules
The command preview should include `docling convert`, plugin flag if enabled, OCR engine flag if selected, one `--to` entry per chosen format, input source, and output destination.

## Error handling
Show immediate message-box errors for invalid setup. For runtime errors, write the error to the log and continue when possible.

## Build expectations for another AI
The implementing AI should build the GUI in Tkinter, keep the code modular, make the UI responsive, make all settings persistent, ensure the final build is suitable for PyInstaller one-file packaging on Windows, and use a clean build process with `build` and `dist` removed before packaging.

## Exact output goal
The expected end result is a Windows executable that opens a Tkinter GUI for batch Docling conversion.
