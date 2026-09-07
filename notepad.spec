# PyInstaller spec file
# Run: pyinstaller notepad.spec
#
# After changing the exclusion lists below, launch the built exe and check
# PDF export and the single-instance handoff before shipping.
#
# onedir on purpose: onefile re-extracts all of PyQt6 into %TEMP% on every
# launch (seconds of startup delay) and UPX both slows extraction and trips
# antivirus heuristics. Keep both off.

import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtNetwork',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt ships far more than a text editor uses, and PyInstaller bundles every
    # module it can reach. None of these are imported anywhere in the app.
    excludes=[
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtQuick3D',
        'PyQt6.QtQuickWidgets',
        'PyQt6.QtWebChannel',
        'PyQt6.QtWebSockets',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtSql',
        'PyQt6.QtTest',
        'PyQt6.QtOpenGL',
        'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtDBus',
        'PyQt6.QtBluetooth',
        'PyQt6.QtNfc',
        'PyQt6.QtPositioning',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtDesigner',
        'PyQt6.QtHelp',
        'PyQt6.QtCharts',
        'PyQt6.QtDataVisualization',
        'PyQt6.QtSpatialAudio',
        # Nothing prints or renders PDF since 4.0 dropped the exporters.
        'PyQt6.QtPdf',
        'PyQt6.QtPdfWidgets',
        'PyQt6.QtPrintSupport',
        'tkinter',
        'pytest',
        'unittest',
        'pydoc_data',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# The `excludes` above only stop Python modules from being imported; the
# PyQt6 hook still copies the whole Qt runtime, so the dead DLLs have to be
# dropped from the collected binaries by hand. Each one below was confirmed
# to have no importer among the Qt libraries the app actually loads.
UNUSED_BINARIES = (
    # Mesa's software OpenGL fallback, ~20 MB — a fifth of the whole build.
    # Loaded only when a GPU driver is missing *and* something asks for GL;
    # QtWidgets paints through the raster engine and never does.
    'opengl32sw.dll',
    # PDF, in both its forms. 4.0 removed the PDF and HTML exporters — the
    # only thing here that ever printed — so neither the viewer module nor
    # the print machinery has an importer left.
    'qt6pdf.dll',
    'qt6printsupport.dll',
    # OpenSSL, pulled in with QtNetwork. The only networking here is a local
    # named pipe for the single-instance guard, which never negotiates TLS.
    'libssl-3.dll',
    'libcrypto-3.dll',
)

a.binaries = TOC(
    entry for entry in a.binaries
    if os.path.basename(entry[0]).lower() not in UNUSED_BINARIES
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NotepadPlus',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NotepadPlus',
)
