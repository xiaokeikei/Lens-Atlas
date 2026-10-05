"""Run the distributable with a sanitized PATH. Fail closed on missing smoke report."""
from pathlib import Path
import argparse
import json
import hashlib
import os
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',default=str(ROOT/'dist'/'LensAtlas'/'LensAtlas.exe'))
    parser.add_argument('--tag',default='packaged')
    parser.add_argument('--mobile-share',action='store_true')
    args=parser.parse_args()
    output=ROOT/'.runtime'/f'{args.tag}-verification.json'
    output.unlink(missing_ok=True)
    env=dict(os.environ)
    env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')+os.pathsep+os.environ['SystemRoot']
    env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
    start=time.monotonic()
    fixture=ROOT/'.runtime'/'合成 测试图库'
    original={str(p.relative_to(fixture)):hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.rglob('*') if p.is_file()}
    command=[args.exe,'--smoke-test','--data-dir',str(ROOT/'.runtime'/f'{args.tag}-verification-data'),'--smoke-fixture',str(fixture),'--smoke-output',str(output)]
    if args.mobile_share:command.append('--smoke-mobile-share')
    p=subprocess.run(command,env=env,cwd=ROOT,timeout=210)
    if p.returncode or not output.exists():
        raise SystemExit(f'Bundled application failed verification (exit {p.returncode}, no report: {not output.exists()})')
    report=json.loads(output.read_text(encoding='utf-8'))
    assert report['window'] is True
    if args.mobile_share:
        assert report['mobile_share']['same_index'] and report['mobile_share']['scan_start_cancel'] and report['mobile_share']['thumbnail'] and report['mobile_share']['directory_management_denied']
        assert report['mobile_share']['menu']=='手机访问'
    assert original=={str(p.relative_to(fixture)):hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.rglob('*') if p.is_file()}, 'Original synthetic source files changed'
    assert '已连接' in report['page']['text']
    assert report['page']['charts']==4
    assert report['stats']['summary']['count']>=31
    assert all(report['tools'].values())
    assert report['jobs'][0]['status']=='completed'
    assert sum(r['count'] for r in report['stats']['cameras'])==25
    assert report['stats']['missing']['any']['count']==18
    assert any(state['metadata_status']=='failed' and state['preview_status']=='failed' and state['count']==1 for state in report['stats']['states']), 'Damaged synthetic RAW must be reported as a read failure'
    assert 'SYNTHETIC' in json.dumps(report) or report['stats']['cameras'][0]['value'].startswith('Synthetic')
    executable=Path(args.exe).resolve()
    video=ROOT/'.runtime'/f'{args.tag}-synthetic-video.mp4'
    ffmpeg=executable.parent/'_internal'/'vendor'/'ffmpeg.exe'
    subprocess.run([str(ffmpeg),'-nostdin','-v','error','-f','lavfi','-i','color=c=green:s=320x240:r=10','-t','1','-c:v','mpeg4','-y',str(video)],check=True,env=env,timeout=30)
    metadata_output=ROOT/'.runtime'/f'{args.tag}-video-metadata.json'
    subprocess.run([str(executable),'--worker','--output',str(metadata_output),'metadata',str(video)],check=True,env=env,timeout=40)
    video_metadata=json.loads(metadata_output.read_text(encoding='utf-8'))
    assert video_metadata['metadata_status']=='ok' and video_metadata['codec']=='mpeg4' and video_metadata['width']==320
    thumbnail_output=ROOT/'.runtime'/f'{args.tag}-video-preview.jpg'
    subprocess.run([str(executable),'--worker','--output',str(metadata_output),'preview',str(video),str(thumbnail_output)],check=True,env=env,timeout=40)
    assert thumbnail_output.is_file() and thumbnail_output.stat().st_size>100
    report['bundled_video_tools_verified']={'metadata':True,'thumbnail':True,'fixture_codec':'mpeg4','browser_playback':'not claimed'}
    report['verification_seconds']=round(time.monotonic()-start,2)
    report['path_isolated']=True
    report['executable_sha256']=hashlib.sha256(executable.read_bytes()).hexdigest()
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'passed','seconds':report['verification_seconds'],'media':report['stats']['summary']['count'],'metadata_cameras':report['stats']['cameras'],'tools':report['tools'],'video_tools':report['bundled_video_tools_verified'],'screenshot':str(output.with_suffix('.png'))},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
