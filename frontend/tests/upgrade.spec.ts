import { acceptUsageNotice } from './notice-helper';
import {test,expect} from '@playwright/test';

test.beforeEach(async({request})=>{
  await request.put('/api/desktop/preferences',{headers:{Authorization:'Bearer synthetic-e2e-local-session'},data:{last_connection:null}});
});

test('cache allows empty draft, validates save and normalizes leading zeros',async({page,request})=>{
  await page.addInitScript(()=>{(window as any).__LENS_TOKEN__='synthetic-e2e-local-session';});
  await page.goto('/');
  await acceptUsageNotice(page);
  await page.getByRole('button',{name:'本机图库'}).click();
  await expect(page.getByRole('heading',{name:'让每一次拍摄，留下线索。'})).toBeVisible();
  let releaseInfo!: () => void;
  const delayedInfo=new Promise<void>(resolve=>{releaseInfo=resolve;});
  await page.route('**/api/info',async route=>{await delayedInfo;await route.continue();});
  const infoResponse=page.waitForResponse(response=>response.url().endsWith('/api/info'));
  await page.getByRole('button',{name:'设置与维护',exact:true}).click();
  const input=page.getByLabel('容量上限（MB）');
  const original=await input.inputValue();
  await input.fill('');
  releaseInfo();
  await infoResponse;
  await expect(input).toHaveValue('');
  await page.getByRole('button',{name:'保存上限',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('空白不会保存');
  await input.fill('008192');
  await page.getByRole('button',{name:'保存上限',exact:true}).click();
  await expect(input).toHaveValue('8192');
  const headers={Authorization:'Bearer synthetic-e2e-local-session'};
  expect((await (await request.get('/api/info',{headers})).json()).cache.limit_bytes).toBe(8192*1024**2);
  await input.fill(original);
  await page.getByRole('button',{name:'保存上限',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('已保存');
});

test('focal overview opens eleven actual values and outside click replaces range',async({page})=>{
  const values=[15,20,35,50,70,85,90,95,100,105,110,115,120,125,135,150,200,300,500,1001].map(value=>({value,count:value===110?50:1,bytes:100}));
  const bounds=[20,40,80,100,120,150,200,300,400,600,1000,null];
  const bins=bounds.map((upper,i)=>{const lower=i?bounds[i-1]!:0;return {value:i,lower,upper,label:i===0?'≤20':upper===null?'>1000':`${lower}–${upper}`,count:values.filter(v=>v.value>lower&&(upper===null||v.value<=upper)).reduce((sum,v)=>sum+v.count,0),bytes:100};});
  await page.addInitScript(()=>{(window as any).__LENS_TOKEN__='synthetic-e2e-local-session';});
  // Controlled UI fixture; backend boundary and filter tests use real database rows.
  await page.route('**/api/stats/focals',route=>route.fulfill({json:{bins,values}}));
  await page.goto('/');
  await acceptUsageNotice(page);
  await page.getByRole('button',{name:'本机图库'}).click();
  await expect(page.locator('.focal-bins button')).toHaveCount(12);
  await page.locator('.focal-bins button').filter({hasText:'100–120 mm'}).click();
  await expect(page.locator('.focal-values button')).toHaveCount(11);
  await expect(page.locator('.focal-detail')).toContainText('以 110 mm 为中心');
  await expect(page.locator('.filter-chips')).toContainText('100–120 mm 区间');
  const query=page.waitForRequest(r=>r.url().endsWith('/api/assets/query')&&r.postDataJSON()?.filters?.focals?.[0]===85);
  await page.locator('.focal-values button').filter({hasText:'85 mm'}).click();
  expect((await query).postDataJSON().filters.focal_bins).toEqual([]);
  await expect(page.locator('.filter-chips')).toContainText('85 mm');
  await expect(page.locator('.filter-chips')).not.toContainText('区间');
  await page.screenshot({path:'../.runtime/upgrade-013-focal.png',fullPage:true});
});

test('desktop and browser both expose read-only comparison configuration',async({page})=>{
  await page.addInitScript(()=>{(window as any).__LENS_TOKEN__='synthetic-e2e-local-session';});
  await page.goto('/');
  await acceptUsageNotice(page);
  await page.getByRole('button',{name:'本机图库'}).click();
  await page.getByRole('button',{name:'图库比对',exact:true}).click();
  await expect(page.getByRole('heading',{name:'图库比对',exact:true})).toBeVisible();
  await expect(page.getByText('只读比对：', {exact:false})).toContainText('不复制、不覆盖、不删除');
  await expect(page.getByLabel('A 图库连接')).toBeVisible();
  await expect(page.getByLabel('B 相对子目录')).toBeVisible();
  await expect(page.getByRole('button',{name:'开始快速比对'})).toBeDisabled();
  await page.screenshot({path:'../.runtime/upgrade-013-comparison.png',fullPage:true});
});
