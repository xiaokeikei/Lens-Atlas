"""A bundled native window with a loopback-only service and no external browser dependency."""
import sys


def main():
    if len(sys.argv)>1 and sys.argv[1] == "--worker":
        from backend.worker import main as worker_main
        worker_main(sys.argv[2:])
        return
    import argparse
    import json
    import os
    import secrets
    import socket
    import threading
    import time
    from pathlib import Path
    import uvicorn
    from PySide6.QtCore import QUrl, QTimer, QLockFile
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineUrlRequestInterceptor
    from backend.app import create_app
    from backend.config import Config, bundle_root
    from backend.native_player import NativePlayer
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--smoke-test', action='store_true', help='Run the real native window, save screenshot and exit')
    parser.add_argument('--smoke-output')
    parser.add_argument('--smoke-fixture',help='Explicit synthetic fixture directory, only with --smoke-test')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    data=Path(args.data_dir or os.getenv('LENS_DATA_DIR') or Path(os.getenv('LOCALAPPDATA',str(Path.home()))) / 'LensAtlas')
    data.mkdir(parents=True,exist_ok=True)
    app=QApplication(sys.argv)
    app.setApplicationName('LensAtlas')
    app.setApplicationDisplayName('镜迹 · Lens Atlas')
    app.setOrganizationName('LensAtlas')
    icon=QIcon(str(bundle_root()/'assets'/'lens-atlas.ico'))
    app.setWindowIcon(icon)
    lock=QLockFile(str(data/'desktop.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None,'镜迹','该本机图库已在另一个窗口运行。请使用现有窗口。')
        return
    token=secrets.token_urlsafe(40)
    config=Config(data_dir=data,desktop=True,local_token=token)
    server_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    server_socket.bind(('127.0.0.1',args.port))
    port=server_socket.getsockname()[1]
    native_player=NativePlayer(app)
    config.native_player=native_player.request
    config.native_player_status=native_player.status
    config.local_origin=f'http://127.0.0.1:{port}'
    service=create_app(config)
    server=uvicorn.Server(uvicorn.Config(service,host='127.0.0.1',port=port,log_config=None,access_log=False,timeout_graceful_shutdown=5))
    server_thread=threading.Thread(target=lambda:server.run(sockets=[server_socket]),daemon=True,name='local-api')
    server_thread.start()
    deadline=time.monotonic()+15
    while not server.started and time.monotonic()<deadline:
        time.sleep(.05)
    if not server.started:
        QMessageBox.critical(None,'镜迹','本地服务未能启动，请检查应用数据目录权限。')
        return
    base=f'http://127.0.0.1:{port}'
    class OnlyLocal(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url=info.requestUrl()
            if url.scheme() in {'data','blob','qrc','about'}:
                return
            if url.scheme()!='http' or url.host()!='127.0.0.1' or url.port()!=port:
                info.block(True)
    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self,url,nav_type,is_main):
            return url.toString().startswith(base+'/') or url.toString()=='about:blank'
    class Window(QMainWindow):
        def closeEvent(self,event):
            native_player.close()
            server.should_exit=True
            event.accept()
    profile=QWebEngineProfile(app)  # Browser stays off-the-record; remembered sessions use Windows DPAPI.
    interceptor=OnlyLocal(profile)
    profile.setUrlRequestInterceptor(interceptor)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    view=QWebEngineView()
    page=LocalPage(profile,view)
    view.setPage(page)
    bootstrap=QWebEngineScript()
    bootstrap.setName('Local session')
    bootstrap.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    bootstrap.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    bootstrap.setRunsOnSubFrames(False)
    bootstrap.setSourceCode('window.__LENS_TOKEN__ = '+json.dumps(token)+';')
    page.scripts().insert(bootstrap)
    if args.smoke_test:
        # Only explicit synthetic smoke runs confirm the notice automatically.
        notice_script=QWebEngineScript()
        notice_script.setName('Synthetic smoke notice confirmation')
        notice_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        notice_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        notice_script.setRunsOnSubFrames(False)
        notice_script.setSourceCode('''
          let attempts=0;
          const noticeTimer=setInterval(()=>{
            const checkbox=document.querySelector('.usage-notice input[type="checkbox"]');
            const button=document.querySelector('.usage-notice button');
            if(checkbox && button){
              if(!checkbox.checked) checkbox.click();
              else if(!button.disabled){button.click();clearInterval(noticeTimer);}
            }
            if(++attempts>=100) clearInterval(noticeTimer);
          },100);
        ''')
        page.scripts().insert(notice_script)
    window=Window()
    window.setWindowTitle('镜迹 · Lens Atlas')
    window.setWindowIcon(icon)
    window.setCentralWidget(view)
    window.resize(1440,960)
    window.setMinimumSize(800,640)
    def download(request):
        # Only explicit user exports; never silently save into a source library.
        target,_=QFileDialog.getSaveFileName(window,'导出只读比对结果',str(Path.home()/'Downloads'/request.suggestedFileName()),'CSV 文件 (*.csv)')
        if not target:
            request.cancel()
            return
        path=Path(target).resolve()
        roots=[Path(r['path']).resolve() for r in service.state.db.rows('SELECT path FROM roots')]
        if any(path.is_relative_to(root) for root in roots):
            request.cancel()
            QMessageBox.warning(window,'原片保护','不能将导出结果写入已添加的素材目录，请选择其他保存位置。')
            return
        request.setDownloadDirectory(str(path.parent))
        request.setDownloadFileName(path.name)
        request.accept()
    profile.downloadRequested.connect(download)
    window.show()
    view.setUrl(QUrl(base+'/'))
    if args.smoke_test:
        output=Path(args.smoke_output or data/'desktop-smoke.json')
        output.parent.mkdir(parents=True,exist_ok=True)
        def capture():
            window.grab().save(str(output.with_suffix('.png')))
            page.runJavaScript('JSON.stringify({title:document.title,text:document.body.innerText,charts:document.querySelectorAll("canvas").length})',lambda result:finish(result))
        def finish(result):
            from backend.query import Filters,statistics
            output.write_text(json.dumps({'url':base,'window':window.isVisible(),'page':json.loads(result or '{}'),'stats':statistics(service.state.db,Filters()),'jobs':service.state.db.rows('SELECT status,phase,errors,message FROM jobs'),'tools':{name:bool(__import__('backend.metadata',fromlist=['tool']).tool(name)) for name in ['exiftool','ffmpeg','ffprobe']}},ensure_ascii=False,indent=2),encoding='utf-8')
            window.close()
            app.quit()
        if args.smoke_fixture:
            import httpx
            client=httpx.Client(base_url=base,headers={'Authorization':'Bearer '+token},trust_env=False)
            roots=client.get('/api/roots').json()
            fixture_path=str(Path(args.smoke_fixture).resolve())
            root=next((r for r in roots if r['path']==fixture_path),None)
            if root is None:
                response=client.post('/api/roots',json={'path':fixture_path,'label':'合成测试图库（非真实相机照片）'})
                response.raise_for_status()
                root=response.json()
            response=client.post(f'/api/roots/{root["id"]}/scan')
            response.raise_for_status()
            job_id=response.json()['id']
            def await_scan():
                row=service.state.db.one('SELECT status FROM jobs WHERE id=?',(job_id,))
                if row['status'] in {'completed','failed'}:
                    QTimer.singleShot(4000,capture)
                else:
                    QTimer.singleShot(1000,await_scan)
            QTimer.singleShot(1000,await_scan)
            QTimer.singleShot(180000,app.quit)
        else:
            QTimer.singleShot(12000,capture)
            QTimer.singleShot(25000,app.quit)
    app.exec()
    server.should_exit=True
    server_thread.join(timeout=config.timeout+10)
    lock.unlock()


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
