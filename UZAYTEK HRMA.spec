# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('static', 'static'), ('*.py', '.')],
    hiddenimports=['scipy', 'numpy', 'plotly', 'trimesh', 'flask', 'PIL', 'tkinter', 'webbrowser', 'threading', 'socket'],
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
    [],
    exclude_binaries=True,
    name='UZAYTEK HRMA',
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
    icon=['static/icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='UZAYTEK HRMA',
)
app = BUNDLE(
    coll,
    name='UZAYTEK HRMA.app',
    icon='static/icon.icns',
    bundle_identifier='com.uzaytek.hrma',
)
