# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['drive.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('v2_ui.py', '.'),
        ('share_panel.py', '.'),
        ('estimate_registry.py', '.'),
        ('license_manager.py', '.'),
        ('process_inspector.py', '.'),
        ('shield_manager.py', '.'),
        ('smart_reader.py', '.'),
        ('config.py', '.'),
        ('models.py', '.'),
        # path_scanner.py excluded — replaced by process_inspector.py
    ],
    hiddenimports=[
        'flask','werkzeug','jinja2','itsdangerous','click',
        'PIL','PIL.Image','markupsafe','charset_normalizer','certifi',
        'charset_normalizer','idna','requests','urllib3',
        'cchardet','brotli','starlette','httpx','anyio','h11','httpcore',
    ],
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
    name='DRIVE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
