# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_data_files

opencc_datas = collect_data_files('opencc', include_py_files=False)

a = Analysis(
    ['ocr_qt.py'],
    pathex=[],
    binaries=[],
    # These modules are imported only when the user invokes the related UI
    # action, so declare them explicitly for PyInstaller.
    datas=opencc_datas,
    hiddenimports=['pandas', 'openpyxl', 'opencc'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ocr_qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['01.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ocr_qt',
)
