"""Fetch official portable tools. Private downloads live in ignored vendor/.

Use --refresh only to deliberately adopt a newer upstream release. A manifest records hashes.
"""
from pathlib import Path
import hashlib
import io
import json
import shutil
import time
import zipfile
import httpx

ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'vendor'
VENDOR.mkdir(exist_ok=True)


def download(url):
    for attempt in range(4):
        try:
            with httpx.Client(follow_redirects=True,timeout=180) as client:
                response=client.get(url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError:
            if attempt==3:raise
            time.sleep(2)


def extract_zip(data, dest):
    dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if not (dest/name).resolve().is_relative_to(dest.resolve()):
                raise ValueError('Unsafe archive path')
        z.extractall(dest)


def main():
    manifest=[]
    exif_url='https://exiftool.org/exiftool-13.59_64.zip'
    # SourceForge is the official Windows download host; direct mirror avoids its HTML UI.
    exif_urls=[exif_url,'https://downloads.sourceforge.net/project/exiftool/exiftool-13.59_64.zip']
    if not (VENDOR/'exiftool'/'exiftool.exe').exists():
        print('Downloading ExifTool 13.59 x64...',flush=True)
        for url in exif_urls:
            try:
                payload=download(url)
                extract_zip(payload,VENDOR/'exiftool')
                exif_url=url
                break
            except (httpx.HTTPError,zipfile.BadZipFile):
                if url==exif_urls[-1]:raise
        executable=next((VENDOR/'exiftool').rglob('exiftool(-k).exe'),None)
        if executable:
            executable.rename(executable.with_name('exiftool.exe'))
        nested=next((VENDOR/'exiftool').rglob('exiftool.exe'))
        if nested.parent!=VENDOR/'exiftool':
            for child in list(nested.parent.iterdir()):
                shutil.move(str(child),str(VENDOR/'exiftool'/child.name))
        manifest.append({'name':'ExifTool','version':'13.59','download':exif_url,'sha256':hashlib.sha256(payload).hexdigest()})
    if not (VENDOR/'ffmpeg.exe').exists():
        print('Downloading LGPL shared FFmpeg / FFprobe...',flush=True)
        asset={'browser_download_url':'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-win64-lgpl-shared-8.1.zip'}
        release={'tag_name':'latest (resolved at download time)'}
        payload=download(asset['browser_download_url'])
        extract_zip(payload,VENDOR/'ffmpeg-package')
        source=next((VENDOR/'ffmpeg-package').rglob('ffmpeg.exe')).parent
        for file in source.iterdir():
            if file.suffix in {'.exe','.dll'} and file.name!='ffplay.exe':
                shutil.copy2(file,VENDOR/file.name)
        manifest.append({'name':'FFmpeg / FFprobe','version':'8.1 LGPL shared','download':asset['browser_download_url'],'sha256':hashlib.sha256(payload).hexdigest(),'upstream_digest':asset.get('digest'),'release':release['tag_name']})
        expected=asset.get('digest','')
        if expected.startswith('sha256:') and expected.split(':')[1]!=hashlib.sha256(payload).hexdigest():
            raise ValueError('FFmpeg archive digest mismatch')
    previous=json.loads((VENDOR/'manifest.json').read_text()) if (VENDOR/'manifest.json').exists() else []
    if not any(item['name']=='ExifTool' for item in previous+manifest):
        manifest.append({'name':'ExifTool','version':'13.59','download':exif_url,'executable_sha256':hashlib.sha256((VENDOR/'exiftool'/'exiftool.exe').read_bytes()).hexdigest()})
    (VENDOR/'manifest.json').write_text(json.dumps(previous+manifest,indent=2),encoding='utf-8')
    print('Portable tool preparation complete.',flush=True)


if __name__=='__main__':main()
