import { test, expect } from '@playwright/test';
import { acceptUsageNotice } from './notice-helper';
import fs from 'node:fs';
import path from 'node:path';

for (const desktop of [true, false]) {
  test(`${desktop ? 'desktop' : 'NAS browser'} confirms once and remembers across reload and browser contexts`, async ({page, request, browser}) => {
    const base=desktop?'http://127.0.0.1:18765':'http://127.0.0.1:18766';
    let token='synthetic-e2e-local-session';
    if(desktop) {
      await request.put('/api/desktop/preferences',{headers:{Authorization:'Bearer '+token},data:{last_connection:null}});
    } else {
      if((await (await request.get(base+'/api/health')).json()).setup_required) {
        const setup_code=fs.readFileSync(path.resolve('..','.runtime/browser-nas-data/setup-code.txt'),'utf8').trim();
        expect((await request.post(base+'/api/auth/setup',{data:{password:'synthetic-nas-password',setup_code}})).ok()).toBeTruthy();
      }
      token=(await (await request.post(base+'/api/auth/login',{data:{password:'synthetic-nas-password'}})).json()).token;
    }
    await page.addInitScript(({desktop,token})=>{
      if(desktop)window.__LENS_TOKEN__=token;
    },{desktop,token});
    // Simulate first use without a production reset API. Save to the real database.
    let accepted=false;
    await page.route('**/api/info',async route=>{
      const response=await route.fetch();
      const info=await response.json();
      if(!response.ok()){await route.fulfill({response});return;}
      await route.fulfill({json:{...info,usage_notice_accepted:accepted?info.usage_notice_accepted:false}});
    });
    let failSave=desktop;
    await page.route('**/api/usage-notice/accept',async route=>{
      if(failSave){failSave=false;await route.fulfill({status:503,json:{detail:'Synthetic save failure'}});return;}
      const response=await route.fetch();
      expect(response.ok()).toBeTruthy();
      accepted=true;
      await route.fulfill({response});
    });
    const dataRequests:string[]=[];
    page.on('request',r=>{if(/\/api\/(roots|jobs|stats|assets)/.test(r.url()))dataRequests.push(r.url());});
    await page.goto(base);
    if(!desktop){
      await expect(page.getByRole('dialog',{name:'使用前请先测试并备份'})).toHaveCount(0);
      await page.getByLabel('管理员密码').fill('synthetic-nas-password');
      await page.getByRole('button',{name:'登录图库'}).click();
    }
    const notice=page.getByRole('dialog',{name:'使用前请先测试并备份'});
    await expect(notice).toBeVisible();
    await expect(notice).toContainText('开发者概不负责');
    await expect(notice).toContainText('仅首次使用时提醒');
    const proceed=page.getByRole('button',{name:'确认并进入镜迹'});
    await expect(proceed).toBeDisabled();
    await page.keyboard.press('Escape');
    await page.keyboard.press('Enter');
    await expect(notice).toBeVisible();
    expect(dataRequests).toEqual([]);
    if(desktop){
      await page.screenshot({path:'../.runtime/usage-notice-desktop.png',fullPage:true});
      await page.setViewportSize({width:390,height:844});
      await expect(proceed).toBeInViewport();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:'../.runtime/usage-notice-mobile.png',fullPage:true});
      await page.getByRole('checkbox',{name:'我已阅读并理解测试、备份建议及风险提示'}).check();
      await proceed.click();
      await expect(notice.getByRole('alert')).toContainText('保存失败');
      expect(dataRequests).toEqual([]);
    }
    await acceptUsageNotice(page);
    await expect(page.locator('.count-pill')).toBeVisible();
    expect((await (await request.get(base+'/api/info',{headers:{Authorization:'Bearer '+token}})).json()).usage_notice_accepted).toBe(true);
    await page.reload();
    await expect(page.locator('.count-pill')).toBeVisible();
    await expect(notice).toHaveCount(0);
    if(!desktop){
      await page.getByTitle('退出登录').click();
      await page.getByLabel('管理员密码').fill('synthetic-nas-password');
      await page.getByRole('button',{name:'登录图库'}).click();
      await expect(page.locator('.count-pill')).toBeVisible();
      await expect(notice).toHaveCount(0);
    }
    const context=await browser.newContext();
    await context.addInitScript(({desktop,token})=>{
      if(desktop)window.__LENS_TOKEN__=token;else sessionStorage.setItem('lens-session',token);
    },{desktop,token});
    const fresh=await context.newPage();
    await fresh.goto(base);
    await expect(fresh.locator('.count-pill')).toBeVisible();
    await expect(fresh.getByRole('dialog',{name:'使用前请先测试并备份'})).toHaveCount(0);
    await context.close();
  });
}
