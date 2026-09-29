from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from backend.app import create_app
from backend.config import Config

ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    nas='--nas' in sys.argv
    app=create_app(Config(data_dir=ROOT/'.runtime'/('browser-nas-data' if nas else 'browser-test-data'),desktop=not nas,local_token='' if nas else 'synthetic-e2e-local-session',allowed_roots=[ROOT/'.runtime'/'合成 测试图库'] if nas else []))
    uvicorn.run(app,host='127.0.0.1',port=18766 if nas else 18765,access_log=False)
