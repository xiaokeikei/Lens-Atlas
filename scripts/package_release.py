from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import __version__


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,default=ROOT/'dist',help='Directory for the verified ZIP and checksum')
    args=parser.parse_args()
    report=ROOT/'.runtime'/'final-verification.json'
    if not report.exists():raise SystemExit('Run verify_bundle.py --tag final successfully before creating the release ZIP.')
    evidence=json.loads(report.read_text(encoding='utf-8'))
    if not evidence.get('path_isolated') or not evidence.get('bundled_video_tools_verified'):
        raise SystemExit('Incomplete packaged application verification.')
    source=ROOT/'dist'/'LensAtlas'
    if evidence.get('executable_sha256') != hashlib.sha256((source/'LensAtlas.exe').read_bytes()).hexdigest():
        raise SystemExit('Executable changed since verification. Run the packaged verification again.')
    for filename in ['README.md','LICENSE','THIRD_PARTY_NOTICES.md','VALIDATION.md','CHANGELOG.md']:
        shutil.copy2(ROOT/filename,source/filename)
    output=args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    target=output/f'LensAtlas-{__version__}-windows-x64.zip'
    count=0
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in source.rglob('*'):
            if file.is_file():
                archive.write(file,Path('LensAtlas')/file.relative_to(source));count+=1
    digest=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
    (target.with_suffix('.zip.sha256')).write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'files':count,'sha256':digest},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
