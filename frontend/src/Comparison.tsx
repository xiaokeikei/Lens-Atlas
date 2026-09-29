import { useCallback, useEffect, useState } from 'react';

type Peer={id:string;name:string;url:string};
type Root={id:number;label:string;status:string;last_scan:string|null};
type Side={connection_id:string|null;root_id:number;subpath:string};
type Api=<T=any>(path:string,body?:unknown,method?:string)=>Promise<T>;
const categories:Record<string,string>={only_left:'仅 A 存在',only_right:'仅 B 存在',different:'内容或大小不同',pending:'待内容校验',same:'内容校验一致',error:'校验异常'};
const state:Record<string,string>={queued:'等待执行',running:'处理中',paused:'已暂停',cancelled:'已取消',failed:'未完成',completed:'已完成'};

function SidePicker({label,value,onChange,api,peers,desktop}:{label:string;value:Side;onChange:(s:Side)=>void;api:Api;peers:Peer[];desktop:boolean}){
  const [roots,setRoots]=useState<Root[]>([]),[error,setError]=useState(''),[password,setPassword]=useState(''),[needsLogin,setNeedsLogin]=useState(false),[refresh,setRefresh]=useState(0);
  const prefix=value.connection_id?`/api/remote/${value.connection_id}`:'';
  useEffect(()=>{let valid=true;setError('');setNeedsLogin(false);setRoots([]);
    api<Root[]>(prefix+'/api/roots').then(r=>{if(valid)setRoots(r);}).catch(e=>{if(valid){setError(e.message);setNeedsLogin(e.status===401);}});
    return()=>{valid=false;};
  },[api,prefix,refresh]);
  return <section className="card compare-side"><h3>{label}</h3><label>图库连接<select aria-label={`${label} 图库连接`} value={value.connection_id||''} onChange={e=>onChange({...value,connection_id:e.target.value||null,root_id:0,subpath:''})}><option value="">{desktop?'本机图库':'当前 NAS'}</option>{peers.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
    {needsLogin&&<form onSubmit={async e=>{e.preventDefault();try{await api(prefix+'/api/auth/login',{password,remember:desktop});setPassword('');setRefresh(v=>v+1);}catch(err:any){setError(err.message);}}}><label>连接密码<input aria-label={`${label} 连接密码`} type="password" value={password} onChange={e=>setPassword(e.target.value)} required autoComplete="current-password"/></label><button type="submit">登录此连接</button><p className="helper">{desktop?'桌面端安全保存会话，不保存明文密码。':'此 NAS 仅在内存保留远端会话，重启后需重新登录。'}</p></form>}
    {error&&<p role="alert" className="helper">{error}</p>}
    <label>素材目录<select aria-label={`${label} 素材目录`} value={value.root_id||''} onChange={e=>onChange({...value,root_id:Number(e.target.value)})}><option value="">请选择已扫描目录</option>{roots.map(r=><option key={r.id} value={r.id}>{r.label} · {r.status==='online'?'已扫描':r.status}</option>)}</select></label>
    <label>相对子目录（可选）<input aria-label={`${label} 相对子目录`} value={value.subpath} onChange={e=>onChange({...value,subpath:e.target.value})} placeholder="例如 旅行/2025；留空比较整个目录"/></label>
    <p className="helper">最后扫描：{roots.find(r=>r.id===value.root_id)?.last_scan||'未选择 / 尚未完成'}</p>
  </section>;
}

export default function Comparison({api,download,desktop}:{api:Api;download:(path:string,name:string)=>Promise<void>;desktop:boolean}){
  const [peers,setPeers]=useState<Peer[]>([]),[left,setLeft]=useState<Side>({connection_id:null,root_id:0,subpath:''}),[right,setRight]=useState<Side>({connection_id:null,root_id:0,subpath:''});
  const [name,setName]=useState(''),[url,setUrl]=useState(''),[adding,setAdding]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [runs,setRuns]=useState<any[]>([]),[selected,setSelected]=useState(''),[result,setResult]=useState<any>(null),[category,setCategory]=useState(''),[offset,setOffset]=useState(0);
  const reload=useCallback(async()=>{setRuns(await api('/api/comparisons'));},[api]);
  useEffect(()=>{let valid=true;api<Peer[]>('/api/peers').then(v=>{if(valid)setPeers(v);}).catch(e=>{if(valid)setError(e.message);});return()=>{valid=false;};},[api]);
  useEffect(()=>{let valid=true;const update=()=>{api<any[]>('/api/comparisons').then(v=>{if(valid)setRuns(v);}).catch(e=>{if(valid)setError(e.message);});};update();const id=setInterval(update,2000);return()=>{valid=false;clearInterval(id);};},[api]);
  useEffect(()=>{if(!selected){setResult(null);return;}let valid=true;const update=()=>api(`/api/comparisons/${selected}?category=${category}&offset=${offset}`).then(v=>{if(valid)setResult(v);}).catch(e=>{if(valid)setError(e.message);});update();const id=setInterval(update,2000);return()=>{valid=false;clearInterval(id);};},[api,selected,category,offset]);
  const start=async(verify:boolean)=>{setBusy(true);setError('');try{const r=await api('/api/comparisons',{left,right,verify});setSelected(r.id);setResult(null);setCategory('');setOffset(0);await reload();}catch(e:any){setError(e.message);}finally{setBusy(false);}};
  const control=async(action:string)=>{try{await api(`/api/comparisons/${selected}/${action}`,{});await reload();}catch(e:any){setError(e.message);}};
  return <div className="comparison-page"><div className="info-note">只读比对：不复制、不覆盖、不删除原片。任务保存在{desktop?'此电脑':'当前 NAS'}，与顶部正在浏览的图库独立。快速结果基于最后完整扫描；内容校验会在两端读取文件计算 SHA-256，可能耗时较长。两端服务均需 0.1.3 或更新版本。</div>
    {error&&<p className="banner error" role="alert">{error}<button onClick={()=>setError('')}>关闭</button></p>}
    <div className="button-row"><button onClick={()=>setAdding(!adding)}>添加比对 NAS</button></div>
    {adding&&<form className="card compare-add" onSubmit={async e=>{e.preventDefault();try{const p=await api<Peer>('/api/peers',{name,url});setPeers(v=>[...v,p]);setRight({...right,connection_id:p.id,root_id:0});setAdding(false);setName('');setUrl('');}catch(err:any){setError(err.message);}}}><label>NAS 名称<input required value={name} onChange={e=>setName(e.target.value)}/></label><label>NAS 地址<input required type="url" placeholder="http://NAS地址:52032" value={url} onChange={e=>setUrl(e.target.value)}/></label><button className="primary">保存比对连接</button></form>}
    <div className="comparison-sides"><SidePicker label="A" value={left} onChange={setLeft} api={api} peers={peers} desktop={desktop}/><SidePicker label="B" value={right} onChange={setRight} api={api} peers={peers} desktop={desktop}/></div>
    <div className="button-row"><button className="primary" disabled={busy||!left.root_id||!right.root_id} onClick={()=>start(false)}>开始快速比对</button><button disabled={busy||!left.root_id||!right.root_id} onClick={()=>start(true)}>完整内容校验并比对</button></div>
    <section className="card"><h3>比对任务</h3><p className="helper">仅操作应用任务与结果；关闭页面后后台继续，暂停或退出桌面服务可恢复。</p>{runs.length===0?<p>尚无比对任务。</p>:<div className="comparison-runs">{runs.map(r=><button key={r.id} className={selected===r.id?'active':''} onClick={()=>{setSelected(r.id);setResult(null);setCategory('');setOffset(0);}}>{new Date(r.created).toLocaleString()} · {state[r.status]||r.status}<small>{r.message}</small></button>)}</div>}</section>
    {result&&<section className="card compare-result"><div className="card-title"><div><h3>比对结果 · {state[result.run.status]}</h3><p>{result.run.message}</p></div><div className="button-row">{['running','queued'].includes(result.run.status)&&<button onClick={()=>control('pause')}>暂停比对</button>}{['paused','failed','cancelled'].includes(result.run.status)&&<button onClick={()=>control('resume')}>恢复比对</button>}{['running','queued','paused'].includes(result.run.status)&&<button onClick={()=>control('cancel')}>取消比对</button>}{result.run.status==='completed'&&<button onClick={()=>download(`/api/comparisons/${selected}/export`,`图库比对-${selected}.csv`).catch(e=>setError(e.message))}>导出 CSV</button>}</div></div>
      <div className="compare-snapshots">{Object.entries(result.run.snapshots||{}).map(([k,v]:[string,any])=><p key={k}>{k==='left'?'A':'B'}：{v.label} / {v.subpath||'全部'} · 扫描时间 {v.last_scan} · 清单 {v.total} 个文件</p>)}</div>
      {result.run.status==='completed'&&<><div className="compare-summary"><button className={!category?'active':''} onClick={()=>{setCategory('');setOffset(0);}}>全部结果</button>{result.summary.map((s:any)=><button key={s.category} className={category===s.category?'active':''} onClick={()=>{setCategory(s.category);setOffset(0);}}><strong>{categories[s.category]} · {s.count}</strong><small>A {(s.left_bytes/1024**2).toFixed(1)} MB / B {(s.right_bytes/1024**2).toFixed(1)} MB</small></button>)}</div>
        <p className="helper">相同路径、相同大小只标为“待内容校验”；内容指纹一致才标为“一致”。两端均不存在的文件无法由此次比对发现。</p>
        <div className="compare-table-wrap"><table><thead><tr><th>相对路径</th><th>结果</th><th>A 字节数</th><th>B 字节数</th></tr></thead><tbody>{result.items.map((r:any)=><tr key={r.relpath}><td title={r.relpath}>{r.relpath}{(r.left_error||r.right_error)&&<small>{r.left_error||r.right_error}</small>}</td><td>{categories[r.category]}</td><td>{r.left_size?.toLocaleString()??'—'}</td><td>{r.right_size?.toLocaleString()??'—'}</td></tr>)}</tbody></table></div>
        <div className="pagination"><button disabled={!offset} onClick={()=>setOffset(v=>Math.max(0,v-100))}>上一页</button><span>{Math.floor(offset/100)+1} / {Math.max(1,Math.ceil(result.total/100))}</span><button disabled={offset+100>=result.total} onClick={()=>setOffset(v=>v+100)}>下一页</button></div>
        {result.move_hints.length>0&&<details><summary>内容一致但路径不同的线索（最多 100 对；不自动移动）</summary>{result.move_hints.map((m:any,i:number)=><p key={i}>{m.left_path} ↔ {m.right_path}</p>)}</details>}
      </>}
    </section>}
  </div>;
}
