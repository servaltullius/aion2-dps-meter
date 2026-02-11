# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/aion2meter/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'winocr',
        'pytesseract',
        'matplotlib.backends.backend_qtagg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='aion2meter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
