import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';

async function mock(page:Page){
  await page.addInitScript(()=>{
    const w=window as any;
    w.__requests=[];
    const assets=Array.from({length:8},(_,i)=>({id:i+1,relpath:`SYNTHETIC-${i+1}.jpg`,kind:i===7?'video':'photo',size:12345678,ext:'jpg',camera:i<4?'Fixture Camera A':'Fixture Camera B',lens:i%2?'Fixture Lens 35':'Fixture Lens 85',taken_at:`2026-0${i%3+1}-05 12:00:00`,focal_native:i%2?35:85,focal_equiv:i===6?null:i%2?50:127,width:1600,height:1200,iso:400,aperture:'2.8',shutter:'1/125',duration:null,metadata_error:null,root_label:'SYNTHETIC FIXTURE',thumbnail_url:'/api/assets/1/thumbnail?expires=123&sig='+'a'.repeat(64)}));
    const status={authorized:true,scope:'全部已授权照片与视频',scanning:false,message:'扫描完成 · 合成验收图库',lastScan:'2026-10-05 · 合成验收图库',revision:1};
    const connections=Array.from({length:3},(_,slot)=>({slot,name:slot===0?'合成 NAS':`连接 ${slot+1}`,url:slot===0?'http://fixture.test:52032':''}));
    const select=(f:any)=>assets.filter(a=>Object.entries({cameras:a.camera,lenses:a.lens,months:a.taken_at.slice(0,7),kinds:a.kind}).every(([key,value])=>!f[key]?.length||f[key].includes(value))&&(!f.search||a.relpath.includes(f.search)));
    const grouped=(items:any[],key:string)=>Object.entries(items.reduce((o,a)=>{if(a[key]!=null){const value=key==='taken_at'?a[key].slice(0,7):a[key];o[value]=(o[value]||0)+1;}return o;},{})).map(([value,count])=>({value:key.startsWith('focal')?Number(value):value,count,bytes:Number(count)*12345678}));
    w.LensAndroid={request:(id:number,action:string,payload:string)=>{
      const args=JSON.parse(payload);w.__requests.push({action,args});let result:any,error:string|undefined;
      const rows=select(args.filters||{});
      switch(action){
        case 'status':result={...status};break;
        case 'bootstrap':result={connections,active:JSON.parse(localStorage.getItem('fixture-active')||'null'),login:null};break;
        case 'restore':result={active:JSON.parse(localStorage.getItem('fixture-active')||'null'),login:null};break;
        case 'selectLocal':localStorage.removeItem('fixture-active');result={ok:true};break;
        case 'forget':localStorage.removeItem('fixture-active');result={ok:true};break;
        case 'connections':result=connections;break;
        case 'stats':result={summary:{count:rows.length,bytes:rows.length*12345678,photos:rows.filter(a=>a.kind==='photo').length,videos:rows.filter(a=>a.kind==='video').length},cameras:grouped(rows,'camera'),lenses:grouped(rows,'lens'),months:grouped(rows,'taken_at'),focals:grouped(rows,args.filters?.mode==='native'?'focal_native':'focal_equiv'),missing:{camera:{count:0},lens:{count:0},time:{count:0},focal:{count:1},any:{count:1}}};break;
        case 'query':result={total:rows.length,items:rows.slice(args.offset,args.offset+24)};break;
        case 'detail':result=assets.find(a=>a.id===args.id);break;
        case 'thumbnail':result='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#d6dfcf"/><circle cx="230" cy="55" r="28" fill="#d79e51"/><path d="M0 190L90 80L175 185L235 110L320 210V240H0Z" fill="#36846c"/><text x="15" y="225" fill="white" font-size="14">SYNTHETIC FIXTURE</text></svg>');break;
        case 'albums':result=[{key:'Fixture-1/',label:'相机 · 合成图库',count:6},{key:'Fixture-2/',label:'截图 · 合成图库',count:2}];break;
        case 'connect':result={slot:args.slot,name:args.name,url:args.url,remembered:args.remember,kind:args.url.includes(':52033')?'computer':'nas'};if(args.remember)localStorage.setItem('fixture-active',JSON.stringify(result));break;
        case 'remoteRoots':result=[{id:1,label:'合成服务端图库',path:'/media/fixture',status:'online',file_count:8,last_scan:null}];break;
        case 'remoteJobs':result=[];break;
        case 'remoteScan':result={id:'12345678-1234-1234-1234-123456789abc',status:'queued'};break;
        case 'scan':status.scanning=true;status.message='已读取 4 个素材 · 元数据异常 0 个';result={started:true};break;
        case 'cancel':status.scanning=false;status.revision++;status.message='扫描已取消，保留上次索引';result={requested:true};break;
        case 'authorize':result={requested:true};break;
        default:error='只读客户端禁止此操作';
      }
      setTimeout(()=>w.__lensReply(id,JSON.stringify({result,error})),15);
    }};
  });
  await page.goto('/mobile.html');
  await expect(page.locator('.mobile-metrics')).toBeVisible();
}
test('shared charts and metrics fit phone width',async({page})=>{
  await mock(page);
  await expect(page.locator('.mobile-metrics .metric')).toHaveCount(4);
  await expect(page.locator('.mobile-charts canvas')).toHaveCount(4);
  await expect(page.locator('.mobile-header .brand')).toContainText('镜迹');
  await expect(page.locator('.mobile-header .brand>div')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:path.resolve('../.runtime/android-react/overview.png'),fullPage:true});
  await page.screenshot({path:path.resolve('../.runtime/android-react/overview-screen.png')});
});
test('computer library uses the same remote scan and browsing entry',async({page})=>{
  await mock(page);await page.getByRole('button',{name:'连接',exact:true}).click();await page.locator('.mobile-library-row').filter({hasText:'合成 NAS'}).click();
  const dialog=page.getByRole('dialog',{name:'连接服务端'});await dialog.getByLabel('连接名称').fill('合成电脑图库');await dialog.getByLabel('镜迹服务地址').fill('http://fixture.test:52033');await dialog.getByLabel('连接密码').fill('synthetic-password');await dialog.getByRole('button',{name:'连接并读取图库'}).click();
  await expect(dialog).not.toBeVisible();await expect(page.locator('.mobile-context')).toContainText('电脑已连接');
  await expect(page.locator('.mobile-header')).toContainText('合成电脑图库');await page.getByRole('button',{name:'扫描',exact:true}).click();await expect(page.getByRole('heading',{name:'服务端只读扫描'})).toBeVisible();
});
test('small phone layout stays within 320 pixels',async({page})=>{
  await page.setViewportSize({width:320,height:720});await mock(page);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await expect(page.locator('.mobile-header .brand>div')).toBeVisible();
});
test('chart selection filters metrics and gallery',async({page})=>{
  await mock(page);
  await page.locator('.chart-options button').filter({hasText:'Fixture Camera A'}).click();
  await expect(page.locator('.mobile-metrics .metric').first().locator('strong')).toHaveText('4');
  await page.getByRole('button',{name:'素材',exact:true}).click();
  await expect(page.locator('.photo-grid .photo')).toHaveCount(4);
  await page.locator('.photo-grid .photo').first().click();
  await expect(page.getByRole('dialog',{name:'素材详情'})).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('Fixture Camera A');
  await page.getByRole('button',{name:'关闭详情'}).click();
  await page.screenshot({path:path.resolve('../.runtime/android-react/gallery.png'),fullPage:true});
});
test('NAS connected state clears connecting message',async({page})=>{
  await mock(page);await page.getByRole('button',{name:'连接',exact:true}).click();
  await page.locator('.mobile-library-row').filter({hasText:'合成 NAS'}).click();
  const dialog=page.getByRole('dialog',{name:'连接服务端'});
  await dialog.getByLabel('连接密码').fill('synthetic-password');
  await dialog.getByRole('button',{name:'连接并读取图库'}).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('.mobile-context')).toContainText('NAS 已连接');
  await expect(page.locator('.mobile-header')).toContainText('合成 NAS');
  await expect(page.locator('.mobile-metrics')).toBeVisible();
  await expect(page.locator('.mobile-content')).not.toContainText('正在连接 NAS');
  await page.screenshot({path:path.resolve('../.runtime/android-react/nas.png'),fullPage:true});
});
test('only selected albums reach native scanner',async({page})=>{
  await mock(page);await page.getByRole('button',{name:'扫描',exact:true}).click();
  await page.getByLabel('相机 · 合成图库').check();
  await page.getByRole('button',{name:'扫描所选 1 个相册'}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__requests.filter((r:any)=>r.action==='scan').length)).toBe(1);
  const requests=await page.evaluate(()=>(window as any).__requests);
  expect(requests.find((r:any)=>r.action==='scan').args.selected).toEqual(['Fixture-1/']);
  await expect(page.getByRole('button',{name:'取消扫描',exact:true})).toBeVisible();
  await page.screenshot({path:path.resolve('../.runtime/android-react/scan.png'),fullPage:true});
});

test('saved login restores after reopening without password prompt',async({page})=>{
  await mock(page);await page.getByRole('button',{name:'连接',exact:true}).click();
  await page.locator('.mobile-library-row').filter({hasText:'合成 NAS'}).click();
  const dialog=page.getByRole('dialog',{name:'连接服务端'});
  await expect(dialog.getByLabel('保持登录（加密保存会话）')).toBeChecked();
  await dialog.getByLabel('连接密码').fill('synthetic-password');await dialog.getByRole('button',{name:'连接并读取图库'}).click();
  await expect(dialog).not.toBeVisible();await page.reload();
  await expect(page.locator('.mobile-header')).toContainText('合成 NAS');
  await expect(page.getByRole('dialog',{name:'连接服务端'})).not.toBeVisible();
  await expect(page.locator('.mobile-metrics')).toBeVisible();
  expect(await page.evaluate(()=>JSON.stringify(localStorage))).not.toContain('synthetic-password');
});
test('NAS scan starts on the selected server without directory mutation',async({page})=>{
  await mock(page);await page.getByRole('button',{name:'连接',exact:true}).click();await page.locator('.mobile-library-row').filter({hasText:'合成 NAS'}).click();
  const dialog=page.getByRole('dialog',{name:'连接服务端'});await dialog.getByLabel('连接密码').fill('synthetic-password');await dialog.getByRole('button',{name:'连接并读取图库'}).click();
  await expect(dialog).not.toBeVisible();await page.getByRole('button',{name:'扫描',exact:true}).click();
  await page.getByRole('button',{name:'增量扫描',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__requests.filter((r:any)=>r.action==='remoteScan').length)).toBe(1);
  const scan=await page.evaluate(()=>(window as any).__requests.find((r:any)=>r.action==='remoteScan'));
  expect(scan.args).toEqual({url:'http://fixture.test:52032',id:1});
  await expect(page.getByText('已请求增量扫描')).toBeVisible();
});
