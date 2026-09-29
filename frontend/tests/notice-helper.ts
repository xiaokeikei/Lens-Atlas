import type { Page } from '@playwright/test';

export async function acceptUsageNotice(page: Page) {
  await page.getByRole('checkbox', {name:'我已阅读并理解测试、备份建议及风险提示'}).check();
  await page.getByRole('button', {name:'确认并进入镜迹'}).click();
}
