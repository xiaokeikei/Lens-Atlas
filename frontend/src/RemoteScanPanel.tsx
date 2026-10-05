import { useEffect, useRef, useState } from 'react';
import { FolderOpen, LoaderCircle, Pause, Play, RefreshCw, ShieldCheck, Square } from 'lucide-react';
import { native } from './androidBridge';
type Root={id:number;label:string;path:string;status:string;file_count:number;last_scan:string|null};
type Job={id:string;root_id:number;root_label:string;status:string;phase:string;processed:number;total:number;enumerated:number;errors:number;message:string|null};
const names:Record<string,string>={queued:'等待扫描',running:'扫描中',paused:'已暂停',completed:'已完成',cancelled:'已取消',failed:'扫描失败',enumerate:'枚举素材',metadata:'读取元数据',preview:'生成预览',complete:'完成'};
export default function RemoteScanPanel({url,onRefresh}:{url:string;onRefresh:()=>void}){
  const [roots,setRoots]=useState<Root[]>([]),[jobs,setJobs]=useState<Job[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const refresh=useRef(onRefresh);refresh.current=onRefresh;const stamp=useRef<string|null>(null);
  const update=async()=>{
    const [r,j]=await Promise.all([native<Root[]>('remoteRoots',{url}),native<Job[]>('remoteJobs',{url})]);
    setRoots(r);setJobs(j);
  };
  useEffect(()=>{
    let valid=true,inFlight=false;stamp.current=null;
    const poll=async()=>{if(inFlight)return;inFlight=true;try{const [r,j]=await Promise.all([native<Root[]>('remoteRoots',{url}),native<Job[]>('remoteJobs',{url})]);if(!valid)return;setRoots(r);setJobs(j);setError('');const next=j.map(job=>`${job.id}:${job.status}:${job.phase}`).join('|');if(stamp.current!==null&&next!==stamp.current)refresh.current();stamp.current=next;}catch(e){if(valid)setError((e as Error).message);}finally{inFlight=false;}};
    poll();const timer=setInterval(poll,2500);return()=>{valid=false;clearInterval(timer);};
  },[url]);
  const act=async(action:()=>Promise<unknown>,message:string)=>{setBusy(true);setError('');try{await action();setNotice(message);await update();refresh.current();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
  return <><section className="card mobile-scan-status"><div className="card-title"><div><h3>服务端只读扫描</h3><p>扫描任务由服务端执行，关闭手机 App 不会停止任务。</p></div><ShieldCheck/></div><p className="helper">仅扫描服务端已经添加的目录。不修改、不上传、不删除原片；只更新服务端的索引、任务记录和预览缓存。</p><button disabled={busy} onClick={()=>act(update,'已刷新扫描状态')}><RefreshCw size={15}/>刷新状态</button></section>{error&&<div className="banner error" role="alert">{error}</div>}{notice&&<div className="banner">{notice}</div>}{!roots.length&&!error&&<section className="card mobile-empty"><FolderOpen/><p>服务端尚未添加素材目录，请先在服务端添加授权目录。</p></section>}{roots.map(root=>{
    const job=jobs.find(j=>j.root_id===root.id&&['queued','running','paused'].includes(j.status))||jobs.find(j=>j.root_id===root.id);
    const running=job&&['queued','running'].includes(job.status);
    return <section className="card mobile-scan-status" key={root.id}><div className="card-title"><div><h3>{root.label||root.path}</h3><p className="mobile-server-path">{root.path}</p></div>{running?<LoaderCircle className="spin" size={18}/>:<FolderOpen size={20}/>}</div><p className="helper">已索引 {Number(root.file_count||0).toLocaleString()} 个素材{root.last_scan?` · 上次扫描 ${root.last_scan}`:''}</p>{job&&<div className="mobile-job"><div><strong>{names[job.status]||job.status}</strong><span>{names[job.phase]||job.phase} · {job.processed} / {job.total||job.enumerated||0}</span></div><progress max={Math.max(job.total,job.enumerated,1)} value={job.processed}/>{job.message&&<p className="helper">{job.message}</p>}{job.errors>0&&<p className="helper">读取异常 {job.errors} 个，其他素材继续处理。</p>}</div>}<div className="button-row"><button className="primary" disabled={busy||!!running} onClick={()=>act(()=>native('remoteScan',{url,id:root.id}),job?.status==='paused'?'已请求恢复扫描':'已请求增量扫描')}><Play size={15}/>{job?.status==='paused'?'恢复扫描':'增量扫描'}</button>{running&&<button disabled={busy} onClick={()=>act(()=>native('remoteControl',{url,id:job.id,action:'pause'}),'已请求暂停扫描')}><Pause size={15}/>暂停</button>}{job&&['queued','running','paused'].includes(job.status)&&<button disabled={busy} onClick={()=>act(()=>native('remoteControl',{url,id:job.id,action:'cancel'}),'已请求取消扫描，已建立的索引保留')}><Square size={14}/>取消</button>}</div></section>;
  })}</>;
}
