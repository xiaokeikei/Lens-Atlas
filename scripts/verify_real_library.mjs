// Explicit opt-in local acceptance test. Private reports stay under ignored .runtime/.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const project=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(project,'frontend/package.json'));
const {chromium}=require('@playwright/test');
const source=process.argv[2];
if(!source || !path.isAbsolute(source) || !fs.statSync(source).isDirectory()) throw new Error('Supply exactly one explicitly authorized absolute media directory.');
const tag=process.argv[3] || 'real-library';
if(!/^[a-z0-9-]+$/i.test(tag)) throw new Error('Invalid report tag');
const output=path.join(project,'.runtime',tag);
fs.mkdirSync(output,{recursive:true});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function inventory(){
  const entries={};
  function walk(dir){for(const d of fs.readdirSync(dir,{withFileTypes:true})){
    const p=path.join(dir,d.name); if(d.isSymbolicLink())continue;
    if(d.isDirectory())walk(p);else if(d.isFile()){const s=fs.statSync(p,{bigint:true});entries[path.relative(source,p)]={size:s.size.toString(),mtime_ns:s.mtimeNs.toString()};}
  }} walk(source);return entries;
}
const before=inventory();fs.writeFileSync(path.join(output,'source-before.json'),JSON.stringify(before));
const exe=path.join(project,'dist/LensAtlas/LensAtlas.exe');
const env={...process.env,QTWEBENGINE_REMOTE_DEBUGGING:'127.0.0.1:19223'};
env.PATH=[path.join(process.env.SystemRoot,'System32'),process.env.SystemRoot].join(path.delimiter);
delete env.PYTHONHOME;delete env.PYTHONPATH;
const app=spawn(exe,['--data-dir',path.join(output,'data'),'--port','18768'],{cwd:project,env,stdio:'ignore'});
fs.writeFileSync(path.join(output,'process.json'),JSON.stringify({pid:app.pid,port:18768,debugPort:19223}));
let browser, page;
const report={source_file_count:Object.keys(before).length,source_bytes:Object.values(before).reduce((a,s)=>a+Number(s.size),0),packaged_executable:true,path_isolated:true,started:new Date().toISOString()};
try{
  for(let i=0;i<100;i++){try{const r=await fetch('http://127.0.0.1:19223/json/version');if(r.ok)break;}catch{}await delay(300);}
  browser=await chromium.connectOverCDP('http://127.0.0.1:19223',{noDefaults:true});
  page=browser.contexts()[0].pages().find(p=>p.url().startsWith('http://127.0.0.1:18768'));
  if(!page)throw new Error('Native app page unavailable');
  await page.waitForFunction(()=>!!window.__LENS_TOKEN__);
  await page.getByRole('checkbox',{name:'我已阅读并理解测试、备份建议及风险提示'}).check();
  await page.getByRole('button',{name:'确认并进入镜迹'}).click();
  const token=await page.evaluate(()=>window.__LENS_TOKEN__);
  async function api(route,body,method){
    const response=await fetch('http://127.0.0.1:18768'+route,{method:method||(body===undefined?'GET':'POST'),headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});
    if(!response.ok)throw new Error('API '+route+' returned '+response.status+': '+await response.text());return response.json();
  }
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.getByRole('button',{name:'目录与扫描',exact:true}).click();
  let roots=await api('/api/roots');
  if(!roots.length){
    await page.getByRole('button',{name:'添加素材目录',exact:true}).click();
    await page.getByLabel('目录路径').fill(source);
    await page.getByLabel('显示名称（可选）').fill('用户授权实测图库');
    await page.getByRole('button',{name:'添加并扫描'}).click();
    for(let i=0;i<30;i++){roots=await api('/api/roots');if(roots.length)break;await delay(200);}
  }else{
    assert.equal(path.resolve(roots[0].path).toLowerCase(),path.resolve(source).toLowerCase());
    const jobs=await api('/api/jobs');
    if(jobs[0]?.status==='paused')await api('/api/jobs/'+jobs[0].id+'/resume',{});
    else await api('/api/roots/'+roots[0].id+'/scan',{});
  }
  const start=Date.now();let job;let previous='';
  for(;;){
    const jobs=await api('/api/jobs');job=jobs[0];
    if(job){const state=job.phase+':'+Math.floor(job.processed/25)+':'+job.status;if(state!==previous){console.log(JSON.stringify({phase:job.phase,processed:job.processed,total:job.total,enumerated:job.enumerated,status:job.status,errors:job.errors,seconds:Math.round((Date.now()-start)/1000)}));previous=state;}
      fs.writeFileSync(path.join(output,'progress.json'),JSON.stringify(job));
      if(['completed','failed','cancelled'].includes(job.status))break;
    }
    if(Date.now()-start>90*60*1000)throw new Error('Acceptance test exceeded 90 minutes; persisted job can resume');
    await delay(2000);
  }
  report.scan_seconds=Number(((Date.now()-start)/1000).toFixed(2));report.job=job;
  assert.equal(job.status,'completed');
  report.equivalent=await api('/api/stats',{});
  report.native=await api('/api/stats',{mode:'native'});
  const all=[];for(let offset=0;;offset+=100){const p=await api('/api/assets/query',{random:false,offset,limit:100});all.push(...p.items);if(all.length>=p.total)break;}
  report.media=all;
  assert.equal(all.length,Object.keys(before).length);
  assert.equal(report.equivalent.summary.bytes,report.source_bytes);
  const uniqueMissing=all.filter(a=>!a.camera||!a.lens||!a.focal_equiv||!a.taken_at);
  assert.equal(report.equivalent.missing.any.count,uniqueMissing.length);
  assert.equal(report.equivalent.missing.any.bytes,uniqueMissing.reduce((n,a)=>n+a.size,0));
  const differingFocal=all.find(a=>a.focal_equiv&&a.focal_native&&a.focal_equiv!==a.focal_native);
  if(differingFocal){
    const eq=await api('/api/assets/query',{filters:{mode:'equivalent',focals:[differingFocal.focal_equiv]},random:false,limit:120});
    const native=await api('/api/assets/query',{filters:{mode:'native',focals:[differingFocal.focal_equiv]},random:false,limit:120});
    assert.ok(eq.items.some(a=>a.id===differingFocal.id));
    assert.ok(!native.items.some(a=>a.id===differingFocal.id));
    report.focal_mode_real_sample={id:differingFocal.id,native:differingFocal.focal_native,equivalent:differingFocal.focal_equiv,passed:true};
  }
  const groups=new Map();
  for(const a of all.filter(a=>a.camera&&a.lens&&a.focal_native)){
    const key=JSON.stringify([a.camera,a.lens,a.focal_native]);
    const group=groups.get(key)||{asset:a,count:0};group.count++;groups.set(key,group);
  }
  const candidate=[...groups.values()].sort((a,b)=>b.count-a.count)[0]?.asset;
  if(candidate){
    const filters={mode:'native',cameras:[candidate.camera],lenses:[candidate.lens],focals:[candidate.focal_native]};
    const expected=all.filter(a=>a.camera===candidate.camera&&a.lens===candidate.lens&&a.focal_native===candidate.focal_native).length;
    const seen=new Set();for(let i=0;i<5;i++){const r=await api('/api/assets/query',{filters,limit:24});assert.equal(r.total,expected);for(const a of r.items){assert.equal(a.camera,candidate.camera);assert.equal(a.lens,candidate.lens);assert.equal(a.focal_native,candidate.focal_native);seen.add(a.id);}}
    report.combined_filter={matching:expected,sampled_unique:seen.size,passed:true};
    if(expected>24)assert.ok(seen.size>24,'Random samples must reach beyond one displayed page');
  }
  await page.getByRole('button',{name:'统计概览',exact:true}).click();
  await page.locator('canvas').first().waitFor();
  await page.locator('.photo').first().waitFor();
  await delay(2000);
  report.qt_media_support=await page.evaluate(()=>{const v=document.createElement('video');return{h264:v.canPlayType('video/mp4; codecs="avc1.42E01E"'),hevc:v.canPlayType('video/mp4; codecs="hvc1"'),vp9:v.canPlayType('video/webm; codecs="vp9"')};});
  const previews=[];
  for(const ext of [...new Set(all.map(a=>a.ext))]){
    const a=all.find(a=>a.ext===ext&&a.preview_status==='ready');if(!a)continue;
    const r=await fetch('http://127.0.0.1:18768'+a.thumbnail_url);const data=Buffer.from(await r.arrayBuffer());
    previews.push({ext,status:r.status,bytes:data.length,id:a.id});assert.equal(r.status,200);assert.equal(data[0],255);assert.equal(data[1],216);
  }
  report.preview_requests=previews;
  const videos=[];
  for(const ext of ['mov','mp4']){
    const v=all.filter(a=>a.ext===ext).sort((a,b)=>b.size-a.size)[0];if(!v)continue;
    const r=await fetch('http://127.0.0.1:18768'+v.stream_url,{headers:{Range:'bytes=0-1023'}});const data=await r.arrayBuffer();
    videos.push({ext,id:v.id,file_bytes:v.size,range_status:r.status,returned_bytes:data.byteLength,content_range:r.headers.get('content-range')});assert.equal(r.status,206);assert.equal(data.byteLength,1024);
  }
  report.video_range=videos;
  const playback=[];
  const combinations=[...new Set(all.filter(a=>a.kind==='video').map(a=>a.ext+':'+a.codec))];
  for(const combination of combinations){
    const v=all.filter(a=>a.kind==='video'&&a.ext+':'+a.codec===combination).sort((a,b)=>a.size-b.size)[0];
    const result=await page.evaluate(url=>new Promise(resolve=>{
      const video=document.createElement('video');video.muted=true;video.preload='auto';
      let finished=false;
      const done=value=>{if(finished)return;finished=true;clearTimeout(timer);video.pause();video.removeAttribute('src');video.load();resolve(value);};
      const timer=setTimeout(()=>done({decoded:false,reason:'timeout',readyState:video.readyState}),12000);
      video.addEventListener('loadeddata',()=>done({decoded:video.videoWidth>0&&video.videoHeight>0,width:video.videoWidth,height:video.videoHeight,duration:video.duration}),{once:true});
      video.addEventListener('error',()=>done({decoded:false,code:video.error?.code,reason:video.error?.message}),{once:true});
      video.src=url;video.load();
    }),v.stream_url);
    playback.push({combination,id:v.id,...result});
  }
  report.actual_qt_video_decode=playback;
  const capabilities=await api('/api/info');
  if(capabilities.native_player_available){
    await page.getByLabel('素材类型').selectOption('video');
    await page.waitForFunction(()=>{const cards=document.querySelectorAll('.photo');return cards.length>0&&cards.length===document.querySelectorAll('.photo .format svg').length;});
    await page.locator('.photo').first().click();
    await page.getByRole('button',{name:'在桌面播放器中打开'}).click();
    let uiPlayer;
    for(let i=0;i<80;i++){uiPlayer=await api('/api/player/status');if(['video_ready','error'].includes(uiPlayer.status))break;await delay(250);}
    assert.equal(uiPlayer.status,'video_ready');assert.ok(uiPlayer.width>0);
    report.native_player_ui_button=true;
    await page.getByRole('button',{name:'关闭素材详情'}).click();
    const native=[];
    for(const combination of combinations){
      const v=all.filter(a=>a.kind==='video'&&a.ext+':'+a.codec===combination).sort((a,b)=>a.size-b.size)[0];
      const opened=await api('/api/player/open',{url:v.stream_url,title:'已授权视频解码验证'});
      let state;
      for(let i=0;i<80;i++){
        state=await api('/api/player/status');
        if(state.request_id===opened.request_id&&['video_ready','error'].includes(state.status))break;
        await delay(250);
      }
      native.push({combination,id:v.id,state});
      assert.equal(state.status,'video_ready');assert.ok(state.width>0&&state.height>0);
      assert.ok((state.width===v.width&&state.height===v.height)||(state.width===v.height&&state.height===v.width),'Decoded frame size must belong to the current clip');
    }
    report.actual_native_video_decode=native;
  }
  report.ui_errors=errors;assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));
  await page.screenshot({path:path.join(output,'overview-private.png'),fullPage:true});
  const incrementalStart=Date.now();const inc=await api('/api/roots/'+roots[0].id+'/scan',{});
  for(;;){const jobs=await api('/api/jobs');const j=jobs.find(j=>j.id===inc.id);if(['completed','failed'].includes(j.status)){assert.equal(j.status,'completed');report.incremental={seconds:Number(((Date.now()-incrementalStart)/1000).toFixed(2)),job:j};break;}await delay(500);}
  assert.deepEqual(inventory(),before,'Source file list, size or modification time changed');report.source_stat_unchanged=true;
  report.completed=new Date().toISOString();
  fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({completed:true,media:all.length,scan_seconds:report.scan_seconds,incremental_seconds:report.incremental.seconds,preview_states:report.equivalent.states,missing:report.equivalent.missing,qt_media_support:report.qt_media_support,source_stat_unchanged:true}));
}catch(e){report.failure=String(e);fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify(report,null,2));throw e;}
finally{
  // WM_CLOSE gives the application its normal service shutdown path; scope to our own PID.
  const close=spawn('powershell.exe',['-NoProfile','-Command',`for ($i=0; $i -lt 3; $i++) { $p=Get-Process -Id ${app.pid} -ErrorAction SilentlyContinue; if ($p) { $null=$p.CloseMainWindow(); Start-Sleep -Milliseconds 500 } }`],{stdio:'ignore'});
  await new Promise(r=>close.on('exit',r));
  await browser?.close().catch(()=>{});
}
