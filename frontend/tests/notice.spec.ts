import { test, expect } from '@playwright/test';
import { acceptUsageNotice } from './notice-helper';

for (const desktop of [true, false]) {
  test(`${desktop ? 'desktop' : 'NAS browser'} requires explicit notice acceptance before using the library`, async ({page}) => {
    if (desktop) await page.addInitScript(() => { window.__LENS_TOKEN__ = 'synthetic-e2e-local-session'; });
    const apiRequests: string[] = [];
    page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()); });
    await page.goto(desktop ? '/' : 'http://127.0.0.1:18766/');
    const notice = page.getByRole('dialog', {name:'使用前请先测试并备份'});
    await expect(notice).toBeVisible();
    await expect(notice).toContainText('开发者概不负责');
    const proceed = page.getByRole('button', {name:'确认并进入镜迹'});
    await expect(proceed).toBeDisabled();
    await page.keyboard.press('Escape');
    await page.keyboard.press('Enter');
    await expect(notice).toBeVisible();
    await expect(page.locator('.app-shell')).toHaveCount(0);
    expect(apiRequests).toEqual([]);
    if (desktop) {
      await page.screenshot({path:'../.runtime/usage-notice-desktop.png', fullPage:true});
      await page.setViewportSize({width:390,height:844});
      await expect(proceed).toBeInViewport();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({path:'../.runtime/usage-notice-mobile.png', fullPage:true});
    }
    await acceptUsageNotice(page);
    await expect(notice).toHaveCount(0);
    await expect(page.locator('.app-shell')).toBeVisible();
    if (desktop) {
      await page.setViewportSize({width:1440,height:1050});
      await page.getByRole('button', {name:'本机图库'}).click();
      await page.getByRole('button', {name:'目录与扫描',exact:true}).click();
      await page.getByRole('button', {name:'添加素材目录',exact:true}).click();
      await expect(page.getByRole('dialog', {name:'添加素材目录'})).toContainText('先用测试文件夹验证无异常');
    }
    await page.reload();
    await expect(notice).toBeVisible();
    await expect(proceed).toBeDisabled();
  });
}
