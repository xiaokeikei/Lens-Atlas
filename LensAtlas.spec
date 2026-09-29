# PyInstaller directory bundle: shared Qt libraries remain individually replaceable (LGPL).
from pathlib import Path
import os
import sys
root = Path(SPECPATH)
# Do not let unrelated developer-tool DLLs on PATH substitute for Windows system DLLs.
os.environ['PATH'] = os.pathsep.join([str(Path(sys.base_prefix)),str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot']])
datas = [(str(root/'frontend'/'dist'), 'frontend/dist'), (str(root/'assets'), 'assets')]
vendor_data = []
if (root/'vendor').is_dir():
    for file in (root/'vendor'/'exiftool').rglob('*'):
        if file.is_file():
            vendor_data.append((str(Path('vendor')/'exiftool'/file.relative_to(root/'vendor'/'exiftool')),str(file),'DATA'))
    for file in (root/'vendor').iterdir():
        if file.is_file():
            vendor_data.append((str(Path('vendor')/file.name),str(file),'DATA'))
    for file in (root/'vendor'/'ffmpeg-package').rglob('LICENSE.txt'):
        vendor_data.append(('vendor/ffmpeg-license/LICENSE.txt',str(file),'DATA'))
if (root/'THIRD_PARTY_NOTICES.md').exists():
    datas.append((str(root/'THIRD_PARTY_NOTICES.md'), '.'))
if (root/'licenses').is_dir():
    datas.append((str(root/'licenses'), 'licenses'))
a = Analysis(['desktop.py'], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=['uvicorn.logging','uvicorn.loops.auto','uvicorn.protocols.http.h11_impl','uvicorn.protocols.websockets.auto','uvicorn.lifespan.on','backend.worker'],
             excludes=['tkinter','matplotlib','numpy','PySide6.QtQml','PySide6.QtQuick','PySide6.Qt3DCore'], noarchive=False)
# Executed tools carry their own adjacent DLLs; never mix them into the Python/Qt loader scope.
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='LensAtlas', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False, icon=str(root/'assets'/'lens-atlas.ico'))
coll = COLLECT(exe,a.binaries,a.datas,vendor_data,strip=False,upx=False,name='LensAtlas')
