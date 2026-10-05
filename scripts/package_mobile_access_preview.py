"""Package the verified opt-in desktop mobile-access preview, without publishing a release."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'dist'/'LensAtlas'
    report=json.loads((ROOT/'.runtime'/'mobile-access-final-verification.json').read_text(encoding='utf-8'))
    assert report['path_isolated'] and report['bundled_video_tools_verified'] and report['mobile_share']['same_index'] and report['mobile_share']['scan_start_cancel']
    assert report['executable_sha256']==hashlib.sha256((source/'LensAtlas.exe').read_bytes()).hexdigest(),'Executable changed after verification'
    for name in ('README.md','VALIDATION.md','LICENSE','THIRD_PARTY_NOTICES.md','CHANGELOG.md'):
        shutil.copy2(ROOT/name,source/name)
    (source/'手机访问使用说明.txt').write_text('镜迹手机访问预览版（基于公开0.1.8，不是已发布正式更新）\n\n1. 关闭旧镜迹，运行此目录LensAtlas.exe；必须保留整个目录和_internal。默认沿用LOCALAPPDATA/LensAtlas中的图库索引。\n2. 菜单“手机访问 → 连接本机图库”（Ctrl+M），勾选允许访问，保存/复制本次连接密码后应用。默认端口52033。\n3. 安卓0.1.3的“连接”填写显示的地址和手机连接密码，勾选保持登录。NAS使用NAS管理员密码；电脑使用本窗口连接密码。\n4. 手机与电脑需在同一局域网或VPN，Windows防火墙须允许本程序专用网络访问。电脑镜迹保持运行。\n5. 手机只查询电脑本机索引，并控制已有目录的扫描任务，不增删目录、不修改/删除原片。查询和扫描复用同一桌面服务与数据库。入口默认关闭，可选择以后启动继续允许。\n6. 修改手机连接密码会撤销旧手机会话；保持登录的会话当前默认30天。\n\n已完成冻结程序回环接口、扫描/统计/预览及原片哈希验证；真实手机WebView/跨Wi-Fi或VPN仍待实机验收。\n',encoding='utf-8')
    target=ROOT.parent/'release'/'LensAtlas-mobile-access-preview-windows-x64.zip'
    target.parent.mkdir(parents=True,exist_ok=True)
    files=[p for p in source.rglob('*') if p.is_file()]
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for i,file in enumerate(files):
            archive.write(file,Path('LensAtlas')/file.relative_to(source))
            if i and i%500==0:print(f'Packaged {i}/{len(files)} files',flush=True)
    with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'files':len(files),'sha256':digest},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
