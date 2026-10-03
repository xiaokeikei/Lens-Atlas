import pytest


def seed(app):
    rid=app.state.db.execute("INSERT INTO roots(path,label,status) VALUES('synthetic','fixture','online')")
    for focal in [None,0,15,20,20.5,21,40,40.1,80,100,100.5,110,120,150,200,300,400,600,1000,1000.5,1001,2000]:
        app.state.db.execute('INSERT INTO assets(root_id,relpath,size,mtime_ns,kind,ext,focal_equiv,focal_native,camera) VALUES(?,?,10,1,\'photo\',\'.jpg\',?,?,?)',
                             (rid,str(focal),focal,50,'Camera'))


def test_decimal_boundaries_no_gaps_zero_excluded_and_selection_applied(env):
    app,c,_=env;seed(app)
    data=c.post('/api/stats/focals',json={}).json()
    assert len(data['bins'])==12
    assert sum(b['count'] for b in data['bins'])==20
    for index,count in [(0,2),(1,3),(4,3),(11,3)]:
        assert data['bins'][index]['count']==count
        values=c.post('/api/assets/query',json={'filters':{'focal_bins':[index]}}).json()
        assert values['total']==count
    selected=c.post('/api/stats/focals',json={'focal_bins':[4]}).json()
    assert sum(b["count"] for b in selected["bins"])==3
    assert [r["value"] for r in selected["values"]]==[100.5,110,120]
    assert c.post('/api/stats/focals',json={'cameras':['different']}).json()['values']==[]
    assert c.post('/api/assets/query',json={'filters':{'focal_bins':[11,0]}}).json()['total']==5
    assert c.post('/api/assets/query',json={'filters':{'focal_bins':[12]}}).status_code==422
    assert c.post('/api/assets/query',json={'filters':{'focal_bins':[-1]}}).status_code==422
    native=c.post('/api/stats/focals',json={'mode':'native'}).json()
    assert native['values']==[{'value':50.0,'count':22,'bytes':220}]


def test_actual_focal_selection_replaces_range_at_api_boundary(env):
    app,c,_=env;seed(app)
    values=c.post('/api/assets/query',json={'filters':{'focals':[20.5],'focal_bins':[]}}).json()
    assert values['total']==1
