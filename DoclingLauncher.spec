# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:/DoclingLauncherApp/main.py'],
    pathex=['E:/DoclingLauncherApp/src'],
    binaries=[],
    datas=[('E:/DoclingLauncherApp/src/docling_launcher/assets/docling_launcher.ico', 'docling_launcher/assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DoclingLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['E:/DoclingLauncherApp/src/docling_launcher/assets/docling_launcher.ico'],
)
