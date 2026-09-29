import { acceptUsageNotice } from './notice-helper';
import { test, expect } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';

test.beforeEach(async({request})=>{
  await request.put('/api/desktop/preferences',{headers:{Authorization:'Bearer synthetic-e2e-local-session'},data:{last_connection:null}});
});

test('real add → scan → charts → filter → random preview → detail → modes',async({page,request})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{(window as any).__LENS_TOKEN__='synthetic-e2e-local-session';});
  await page.goto('/');
  await acceptUsageNotice(page);
  await expect(page.getByRole('heading',{name:'让每一次拍摄，留下线索。'})).toBeVisible();
  await page.getByRole('button',{name:'目录与扫描',exact:true}).click();
  const headers={Authorization:'Bearer synthetic-e2e-local-session'};
  let roots=await (await request.get('/api/roots',{headers})).json();
  if(!roots.length){
    await page.getByRole('button',{name:'添加素材目录',exact:true}).click();
    await page.getByLabel('目录路径').fill(path.resolve('..','.runtime','合成 测试图库'));
    await page.getByLabel('显示名称（可选）').fill('明确标记的合成测试图库');
    await page.getByRole('button',{name:'添加并扫描'}).click();
  }else{await page.getByRole('button',{name:'增量扫描',exact:true}).first().click();}
  await expect.poll(async()=>{const j=await (await request.get('/api/jobs',{headers})).json();return j[0]?.status;},{timeout:90000}).toBe('completed');
  await page.getByRole('button',{name:'统计概览',exact:true}).click();
  await expect(page.locator('canvas')).toHaveCount(4);
  await expect(page.locator('.photo')).toHaveCount(24);
  const total=Number((await page.locator('.count-pill').innerText()).replaceAll(',',''));
  expect(total).toBeGreaterThanOrEqual(31);
  await expect(page.locator('.photo-grid.loading')).toHaveCount(0);
  await expect(page.locator('.photo-image .spin')).toHaveCount(0,{timeout:30000});
  await page.screenshot({path:'../.runtime/browser-overview.png',fullPage:true});
  await page.locator('.chart-options button').filter({hasText:'Synthetic Camera A'}).click();
  await expect(page.locator('.filter-chips')).toContainText('Synthetic Camera A');
  await expect.poll(async()=>Number((await page.locator('.count-pill').innerText()).replaceAll(',',''))).toBeLessThan(total);
  await page.getByRole('button',{name:'换一批',exact:true}).click();
  await page.locator('.photo').first().click();
  const detail=page.getByRole('dialog',{name:'素材详情'});
  await expect(detail).toBeVisible();
  await expect(detail.locator('dl')).toContainText('Synthetic Camera A');
  await expect(detail.locator('dl')).toContainText('35mm 等效焦距');
  await page.getByRole('button',{name:'关闭素材详情'}).click();
  await page.getByRole('button',{name:'原生焦距',exact:true}).click();
  await expect(page.locator('.soft-label').filter({hasText:'真实索引'})).toContainText('原生');
  await page.getByRole('button',{name:'重置',exact:true}).click();
  await page.getByRole('button',{name:'顺序浏览',exact:true}).click();
  await page.getByRole('button',{name:'下一页',exact:true}).click();
  await expect(page.locator('.pagination')).toContainText('2 / 2');
  await page.getByRole('button',{name:'设置与维护',exact:true}).click();
  await expect(page.getByRole('heading',{name:'服务与工具'})).toBeVisible();
  await page.setViewportSize({width:600,height:900});
  await page.getByRole('button',{name:'统计概览',exact:true}).click();
  await page.screenshot({path:'../.runtime/browser-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('NAS login, background scanning and independent browser filters',async({page,request,browser})=>{
  const base='http://127.0.0.1:18766';
  const health=await (await request.get(base+'/api/health')).json();
  if(health.setup_required){
    const code=fs.readFileSync(path.resolve('..','.runtime','browser-nas-data','setup-code.txt'),'utf8').trim();
    expect((await request.post(base+'/api/auth/setup',{data:{password:'synthetic-nas-password',setup_code:code}})).ok()).toBeTruthy();
  }
  await page.addInitScript(()=>{(window as any).__LENS_TOKEN__='synthetic-e2e-local-session';});
  await page.goto('/');
  await acceptUsageNotice(page);
  await expect(page.locator('.count-pill')).toContainText('31');
  await page.getByRole('button',{name:'连接 NAS'}).click();
  await page.getByLabel('连接名称').fill('浏览器测试 NAS');
  await page.getByLabel('服务地址').fill(base);
  await page.getByRole('button',{name:'保存并连接'}).click();
  await expect(page.getByRole('heading',{name:'连接你的图库'})).toBeVisible();
  await page.getByLabel('管理员密码').fill('synthetic-nas-password');
  await expect(page.getByLabel('保持登录并自动连接')).toBeChecked();
  await page.getByRole('button',{name:'登录图库'}).click();
  await expect(page.locator('.breadcrumb')).toContainText('浏览器测试 NAS');
  await expect(page.getByRole('heading',{name:'让每一次拍摄，留下线索。'})).toBeVisible();
  await page.getByRole('button',{name:'目录与扫描',exact:true}).click();
  const localHeaders={Authorization:'Bearer synthetic-e2e-local-session'};
  const logged=await (await request.post(base+'/api/auth/login',{data:{password:'synthetic-nas-password'}})).json();
  const remoteHeaders={Authorization:'Bearer '+logged.token};
  const roots=await (await request.get(base+'/api/roots',{headers:remoteHeaders})).json();
  if(!roots.length){
    await page.getByRole('button',{name:'添加素材目录',exact:true}).click();
    await page.getByLabel('目录路径').fill(path.resolve('..','.runtime','合成 测试图库'));
    await page.getByRole('button',{name:'添加并扫描'}).click();
  }else await page.getByRole('button',{name:'增量扫描',exact:true}).first().click();
  await expect(page.locator('.job-row').first()).toBeVisible();
  await page.close();
  await expect.poll(async()=>{const jobs=await (await request.get(base+'/api/jobs',{headers:remoteHeaders})).json();return jobs[0]?.status;},{timeout:90000}).toBe('completed');
  const context=await browser.newContext();
  const browserPage=await context.newPage();
  await browserPage.goto(base);
  await acceptUsageNotice(browserPage);
  await browserPage.getByLabel('管理员密码').fill('synthetic-nas-password');
  await browserPage.getByRole('button',{name:'登录图库'}).click();
  await expect(browserPage.locator('.count-pill')).toContainText('31');
  await browserPage.locator('.chart-options button').filter({hasText:'Synthetic Camera B'}).click();
  await expect(browserPage.locator('.filter-chips')).toContainText('Synthetic Camera B');
  const all=await (await request.post(base+'/api/stats',{headers:remoteHeaders,data:{}})).json();
  expect(all.summary.count).toBe(31);
  await browserPage.locator('.photo').first().click();
  await expect(browserPage.getByRole('dialog',{name:'素材详情'})).toBeVisible();
  await context.close();
  const desktopPage=await browser.newPage();
  await desktopPage.addInitScript(()=>{(window as any).__LENS_TOKEN__='synthetic-e2e-local-session';});
  await desktopPage.goto('http://127.0.0.1:18765/');
  await acceptUsageNotice(desktopPage);
  await expect(desktopPage.locator('.breadcrumb')).toContainText('浏览器测试 NAS');
  await expect(desktopPage.getByRole('heading',{name:'让每一次拍摄，留下线索。'})).toBeVisible();
  await desktopPage.getByRole('button',{name:'本机图库'}).click();
  await expect(desktopPage.locator('.breadcrumb')).toContainText('本机图库');
  await expect(desktopPage.locator('.count-pill')).toContainText('31');
  const saved=await (await request.get('/api/connections',{headers:localHeaders})).json();
  expect(saved.some((c:any)=>c.name==='浏览器测试 NAS')).toBeTruthy();
  await desktopPage.close();
});
