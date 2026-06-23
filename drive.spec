# DRIVE — PyInstaller build spec
# Run: pyinstaller drive.spec --noconfirm

from PyInstaller.building.build_main import Analysis
from PyInstaller.building.api import EXE, COLLECT, PYZ
import os
from pathlib import Path

ROOT = Path(os.getcwd())

a = Analysis(
    [str(ROOT / "drive.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "icon.ico"), ".") if (ROOT / "icon.ico").exists() else None,
    ],
    hiddenimports=[
        "flask",
        "werkzeug",
        "jinja2",
        "markupsafe",
        "smart_reader",
        "path_scanner",
        "shield_manager",
        "models",
        "config",
        "app",
        "web_ui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "tkinter",
        "test",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DRIVE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "icon.ico") if (ROOT / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DRIVE",
)