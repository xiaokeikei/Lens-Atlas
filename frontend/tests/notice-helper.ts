import { expect, type Page } from '@playwright/test';

export async function acceptUsageNotice(page: Page) {
  const notice=page.getByRole('dialog', {name:'使用前请先测试并备份'});
  await expect(notice.or(page.locator('.count-pill'))).toBeVisible();
  if(await notice.isVisible()) {
    await page.getByRole('checkbox', {name:'我已阅读并理解测试、备份建议及风险提示'}).check();
    await page.getByRole('button', {name:'确认并进入镜迹'}).click();
    await expect(notice).toHaveCount(0);
  }
}
