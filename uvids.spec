# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


BASE_DIR = Path(SPECPATH).resolve()
APP_DIR = BASE_DIR / 'app'
ASSETS_DIR = APP_DIR / 'assets'
MAIN_SCRIPT = APP_DIR / 'main.py'
IS_WINDOWS = sys.platform.startswith('win')

datas = [(str(ASSETS_DIR), 'app/assets')]

hiddenimports = ['yt_dlp', 'PIL', 'PIL.Image', 'PIL.ImageTk']
icon = str(ASSETS_DIR / 'icons' / 'uvids.ico') if IS_WINDOWS else None

a = Analysis(
    [str(MAIN_SCRIPT)],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='uvids',
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
    icon=icon,
)
