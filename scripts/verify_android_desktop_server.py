"""Isolated live desktop-library gateway for phone integration checks; synthetic files only."""
from contextlib import asynccontextmanager
from pathlib import Path
import hashlib
import json
import secrets
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw
from fastapi.testclient import TestClient
import uvicorn
from backend.app import create_app
from backend.config import Config
from backend.mobile_share import create_gateway


def main():
    staging=ROOT/'.runtime'/'desktop-mobile-validation'
    staging.mkdir(parents=True,exist_ok=True)
    session=Path(tempfile.mkdtemp(prefix='fixture-',dir=staging))
    media=session/'synthetic-media';media.mkdir()
    for i in (1,2):
        image=Image.new('RGB',(320,240),'#257b64')
        ImageDraw.Draw(image).text((15,100),f'SYNTHETIC DESKTOP {i} - NOT REAL PHOTO',fill='white')
        exif=Image.Exif();exif[272]='SYNTHETIC Desktop Camera'
        image.save(media/f'SYNTHETIC-{i}.jpg',exif=exif)
    def hashes():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    original=hashes()
    config=Config(data_dir=session/'app-data',desktop=True,local_token=secrets.token_urlsafe(40))
    prepare=create_app(config,start_scanner=False)
    with TestClient(prepare) as local:
        local.headers['Authorization']='Bearer '+config.local_token
        root=local.post('/api/roots',json={'path':str(media),'label':'SYNTHETIC DESKTOP'}).json()
        job=local.post(f'/api/roots/{root["id"]}/scan',json={}).json()
        prepare.state.scanner.run_job(job)
        assert local.post('/api/stats',json={}).json()['summary']['count']==2
    service=create_app(config)
    gateway=create_gateway(service)
    gateway.state.credentials.set_password('AndroidFixture123!')
    gateway_lifespan=gateway.router.lifespan_context
    @asynccontextmanager
    async def running(app):
        async with service.router.lifespan_context(service):
            async with gateway_lifespan(app):yield
    gateway.router.lifespan_context=running
    requests=[]
    @gateway.middleware('http')
    async def observe(request,call_next):
        response=await call_next(request)
        requests.append({'method':request.method,'path':request.url.path,'status':response.status_code})
        assert hashes()==original,'Synthetic desktop source bytes changed'
        (staging/'requests.json').write_text(json.dumps(requests,indent=2),encoding='utf-8')
        (staging/'source-integrity.json').write_text(json.dumps({'unchanged':True,'sha256':original}),encoding='utf-8')
        return response
    print('Synthetic desktop gateway ready at 127.0.0.1:18769',flush=True)
    uvicorn.run(gateway,host='127.0.0.1',port=18769,access_log=False,proxy_headers=False)


if __name__=='__main__':main()
