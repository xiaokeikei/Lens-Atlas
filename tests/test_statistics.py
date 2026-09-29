import json
import pytest
from backend.metadata import normalize
from backend.query import Filters,statistics


def seed(db):
    rid=db.execute("INSERT INTO roots(path,label) VALUES('/synthetic','fixture')")
    rows=[('a.jpg',100,'Camera A','Lens A',35,50,'2024-01-01T12:00:00','ok','ready'),
          ('b.jpg',200,'Camera A',None,50,None,'2024-02-01T12:00:00','ok','failed'),
          ('c.nef',300,None,None,85,85,None,'ok','failed'),
          ('d.jpg',400,'Camera B','Lens B',24,24,'2025-01-01T12:00:00','ok','ready'),
          ('e.cr3',500,None,None,None,None,None,'failed','failed')]
    for p,size,c,l,n,e,t,m,preview in rows:
        db.execute('INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext,camera,lens,focal_native,focal_equiv,taken_at,metadata_status,preview_status) VALUES(?,?,?,1,\'photo\',\'jpg\',?,?,?,?,?,?,?)',(rid,p,size,c,l,n,e,t,m,preview))
    db.execute("INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext) VALUES(?,'notes.txt',9999,1,'nonmedia','txt')",(rid,))
    return rid


def test_partial_fields_missing_union_and_bytes(env):
    app,c,_=env; seed(app.state.db)
    s=c.post('/api/stats',json={}).json()
    assert s['summary']['count']==5 and s['summary']['bytes']==1500
    assert s['missing']['any']=={'count':3,'bytes':1000}
    assert s['missing']['lens']=={'count':3,'bytes':1000}
    assert s['missing']['camera']=={'count':2,'bytes':800}
    assert s['missing']['focal']=={'count':2,'bytes':700}
    assert next(g for g in s['cameras'] if g['value']=='Camera A')['count']==2
    assert sum(g['count'] for g in s['months'])==3
    assert sum(g['count'] for g in s['focals'])==3  # RAW preview failure retains valid focal.


def test_focal_modes_and_filters_are_consistent(env):
    app,c,_=env;seed(app.state.db)
    eq=c.post('/api/assets/query',json={'filters':{'mode':'equivalent','focals':[50]}}).json()
    native=c.post('/api/assets/query',json={'filters':{'mode':'native','focals':[50]}}).json()
    assert [x['relpath'] for x in eq['items']]==['a.jpg']
    assert [x['relpath'] for x in native['items']]==['b.jpg']
    s=c.post('/api/stats',json={'mode':'native'}).json()
    assert s['missing']['focal']=={'count':1,'bytes':500}


def test_no_unreliable_equivalence_or_mtime_fallback():
    v=normalize({'EXIF:FocalLength':35,'Composite:FocalLength35efl':52.5,'File:FileModifyDate':'2025:01:02 10:00:00'})
    assert v['focal_native']==35 and v['focal_equiv'] is None and v['taken_at'] is None
    v=normalize({'EXIF:FocalLength':35,'EXIF:FocalLengthIn35mmFormat':50,'EXIF:DateTimeOriginal':'2024:05:06 12:30:00','EXIF:OffsetTimeOriginal':'+08:00'})
    assert v['focal_equiv']==50 and v['focal_source']=='EXIF:FocalLengthIn35mmFormat'
    assert v['taken_at']=='2024-05-06T12:30:00+08:00'
    assert normalize({'DateTimeOriginal':'0000:00:00 00:00:00'})['taken_at'] is None


def test_combination_and_random_uses_entire_filtered_population(env):
    app,c,_=env;rid=seed(app.state.db)
    for i in range(150):
        app.state.db.execute("INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext,camera,lens,focal_equiv) VALUES(?,?,10,1,'photo','jpg','Camera A','Bulk Lens',50)",(rid,f'bulk-{i:03}.jpg'))
    filters={'cameras':['Camera A'],'lenses':['Bulk Lens'],'focals':[50]}
    seen=set()
    for _ in range(20):
        data=c.post('/api/assets/query',json={'filters':filters,'limit':10}).json()
        assert data['total']==150
        assert len({r['id'] for r in data['items']})==10
        assert all(r['camera']=='Camera A' and r['lens']=='Bulk Lens' and r['focal_equiv']==50 for r in data['items'])
        seen.update(r['id'] for r in data['items'])
    assert len(seen)>60
    page=c.post('/api/assets/query',json={'filters':filters,'limit':10,'random':False,'offset':140}).json()
    assert len(page['items'])==10


def test_missing_filter_intersection_and_injection_safety(env):
    app,c,_=env;seed(app.state.db)
    s=c.post('/api/stats',json={'cameras':['Camera A'],'missing':['lens']}).json()
    assert s['summary']['count']==1 and s['summary']['bytes']==200
    assert c.post('/api/stats',json={'cameras':["' OR 1=1 --"]}).json()['summary']['count']==0
    assert c.post('/api/stats',json={'search':'%'}).json()['summary']['count']==0
    assert c.post('/api/stats',json={'mode':'made-up'}).status_code==422


def test_raw_plus_jpeg_remain_separate(env):
    app,c,_=env;rid=seed(app.state.db)
    app.state.db.execute("INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext) VALUES(?,'a.cr3',100,1,'photo','cr3')",(rid,))
    assert c.post('/api/stats',json={}).json()['summary']['count']==6
