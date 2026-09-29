from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Config


def make_jpeg(path: Path, camera='Test Camera A', lens='Test Lens 35', native=35, equiv=50, date='2024:05:06 12:30:00', color='#315b44'):
    path.parent.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(640,420),color)
    draw=ImageDraw.Draw(im)
    draw.rectangle((50,60,270,290),fill='#d6caa4')
    draw.ellipse((300,100,550,350),fill='#98b1a1')
    draw.text((35,385),'SYNTHETIC TEST FIXTURE - NOT A REAL CAMERA PHOTO',fill='white')
    exif=Image.Exif()
    if camera:exif[272]=camera
    detail={33437:2.8,33434:1/125,34855:400}
    if lens:detail[42036]=lens
    if native:detail[37386]=native
    if equiv:detail[41989]=equiv
    if date:detail[36867]=date
    exif[34665]=detail
    im.save(path,format='JPEG',exif=exif)
    return path


@pytest.fixture
def env(tmp_path):
    config=Config(data_dir=tmp_path/'app data',desktop=True,local_token='test-local-token',timeout=20)
    app=create_app(config,start_scanner=False)
    with TestClient(app) as client:
        client.headers['Authorization']='Bearer test-local-token'
        yield app,client,tmp_path


def add_scan(app,client,path,force=False):
    roots=client.get('/api/roots').json()
    root=next((r for r in roots if Path(r['path'])==path.resolve()),None)
    if not root:
        response=client.post('/api/roots',json={'path':str(path),'label':'合成测试图库'})
        assert response.status_code==200,response.text
        root=response.json()
    response=client.post(f"/api/roots/{root['id']}/scan?force={str(force).lower()}")
    assert response.status_code==200,response.text
    app.state.scanner.run_job(response.json())
    return root,app.state.db.one('SELECT * FROM jobs WHERE id=?',(response.json()['id'],))
