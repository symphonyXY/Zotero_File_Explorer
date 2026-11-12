# PyInstaller one-directory build: Qt stays dynamically replaceable (LGPL).
from pathlib import Path
root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / 'scripts/entry.py')],
    pathex=[str(root / 'src')],
    datas=[
        (str(root / 'assets/icons/app.ico'), 'assets/icons'),
        (str(root / 'assets/icons/app.png'), 'assets/icons'),
    ],
    hiddenimports=[],
    excludes=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtOpenGL', 'PySide6.QtTest'],
    noarchive=False,
)
# Qt 6.10 uses the ICU API supplied by Windows 10/11. A development PATH may
# contain Poppler's incompatible, version-suffixed icuuc.dll. Never bundle that
# DLL in place of the OS API. The Widgets raster UI also needs no Mesa fallback.
analysis.binaries = [entry for entry in analysis.binaries
    if not (Path(entry[0]).name.lower().startswith('icu') and entry[0].lower().endswith('.dll'))
    and Path(entry[0]).name.lower() != 'opengl32sw.dll']
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
          name='ZoteroFileExplorer', debug=False, strip=False, upx=False,
          console=False, icon=str(root / 'assets/icons/app.ico'))
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False,
                     name='ZoteroFileExplorer')
