from pathlib import Path
import importlib.metadata as md
import json
import shutil
import httpx
import time

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'licenses'


def main():
    DEST.mkdir(exist_ok=True)
    names=['fastapi','starlette','uvicorn','pydantic','pydantic_core','httpx','httpcore','anyio','certifi','idna','h11','click','pillow','typing_extensions','typing_inspection','annotated_types','annotated_doc','PySide6','PySide6_Essentials','PySide6_Addons','shiboken6']
    manifest=[]
    for name in names:
        dist=md.distribution(name)
        manifest.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),'source':dist.metadata.get_all('Project-URL')})
        for entry in dist.files or []:
            if any(s in entry.name.lower() for s in ['license','copying','notice']) and '.dist-info' in str(entry):
                dest=DEST/name/entry.name
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(dist.locate_file(entry),dest)
    for name in ['react','react-dom','scheduler','echarts','zrender','tslib','lucide-react']:
        package=ROOT/'frontend'/'node_modules'/name
        if not package.exists():continue
        info=json.loads((package/'package.json').read_text(encoding='utf-8'))
        manifest.append({'name':name,'version':info['version'],'license':info.get('license'),'source':info.get('repository')})
        for entry in package.iterdir():
            if entry.is_file() and any(s in entry.name.lower() for s in ['license','copying','notice']):
                dest=DEST/name/entry.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(entry,dest)
    # Qt wheel metadata omits open-source license texts: retrieve official license documents.
    shutil.copy2(next((ROOT/'vendor'/'ffmpeg-package').rglob('LICENSE.txt')),DEST/'LGPL-3.0.txt')
    shutil.copy2(ROOT/'vendor'/'exiftool'/'exiftool_files'/'LICENSE',DEST/'GPL-3.0.txt')
    urls={'Qt-WebEngine-licensing.html':'https://doc.qt.io/qt-6/qtwebengine-licensing.html',
          'Python-LICENSE.txt':'https://raw.githubusercontent.com/python/cpython/v3.12.10/LICENSE'}
    for filename,url in urls.items():
        if (DEST/filename).exists():continue
        print('Retrieving',filename,flush=True)
        for attempt in range(4):
            try:
                r=httpx.get(url,follow_redirects=True,timeout=45);r.raise_for_status()
                break
            except httpx.HTTPError:
                if attempt==3:raise
                time.sleep(1)
        (DEST/filename).write_bytes(r.content)
    manifest.append({'name':'Qt/PySide6 open-source sources','version':md.version('PySide6'),'source':'https://download.qt.io/official_releases/QtForPython/pyside6/ and https://download.qt.io/official_releases/qt/','replacement':'Replace shared libraries in _internal/PySide6 with ABI-compatible builds; no signature restriction.'})
    (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Collected license texts for',len(manifest),'components.')


if __name__=='__main__':main()
