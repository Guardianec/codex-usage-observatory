import {test,expect} from '@playwright/test';

test('overview displays real API totals, live chart modes, and local identity',async({page,request})=>{
  const data=await(await request.get('/api/analytics')).json();expect(data.summary.request_count).toBeGreaterThan(0);
  await page.goto('/?range=all');await expect(page.getByRole('heading',{name:'Overview',exact:true})).toBeVisible();
  await expect(page.getByText('Collector connected',{exact:true})).toBeVisible();
  await expect(page.locator('.big-number')).toContainText('10,200');
  await page.getByLabel('Chart mode').selectOption('rate');await expect(page.locator('.chart-caption').first()).toContainText('Tokens / minute');
  await page.locator('.chart-wrap svg').first().focus();await page.keyboard.press('ArrowRight');await expect(page.locator('.chart-tooltip').first()).toBeVisible();
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));expect(errors).toEqual([]);
});
test('task table sorts, filters, searches, paginates and supports deep refresh',async({page})=>{
  await page.goto('/tasks?range=all');await expect(page.locator('.pagination')).toContainText('of 32');
  await page.getByRole('button',{name:'Total',exact:true}).click();await expect(page).toHaveURL(/sort=-total_tokens/);
  await expect(page.locator('.total-cell').first()).toHaveText('326.4K');
  await page.getByLabel('Model filter').selectOption('fixture-model-a');await expect(page.locator('.pagination')).toContainText('of 16');
  await page.getByLabel('Search turns').fill('qa-thread-31');await expect(page).toHaveURL(/search=qa-thread-31/);await expect(page.locator('.pagination')).toHaveText(/^1–1 of 1/);
  await page.locator('.task-link').first().click();await expect(page.getByRole('heading',{name:'Turn detail',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Model responses',exact:true})).toBeVisible();
  await page.reload();await expect(page.locator('.detail-tokens')).toContainText('326,400');
  await page.goBack();await expect(page.getByLabel('Search turns')).toHaveValue('qa-thread-31');
  await page.goBack();await expect(page.getByLabel('Search turns')).toHaveValue('');
});
test('session and project drilldowns and model comparisons work',async({page})=>{
  await page.goto('/sessions?range=all');await page.locator('.session-row').first().click();await expect(page.getByRole('heading',{name:'Turn sequence',exact:true})).toBeVisible();
  await page.goto('/projects?range=all');await page.locator('.project-item').first().click();await expect(page.getByRole('heading',{name:'Project usage',exact:true})).toBeVisible();
  await page.goto('/models?range=all');await expect(page.locator('.model-table')).toContainText('fixture-model-a');await page.getByLabel('Comparison metric').selectOption('median_duration_seconds');
  await page.getByLabel('Effort filter').selectOption('high');await expect(page.locator('.model-table tbody tr')).toHaveCount(1);
});
test('custom ranges, empty and unavailable states stay honest',async({page})=>{
  await page.goto('/?range=custom&from=2000-01-01&to=2000-01-02');await expect(page.getByText('No usage in this period',{exact:true})).toBeVisible();
  await page.goto('/agents?range=all');await expect(page.getByRole('heading',{name:'No explicit child relationships in this range'})).toBeVisible();
  await page.goto('/tasks/missing/missing');await expect(page.getByRole('alert')).toContainText('This record is unavailable');
});
test('settings persist theme, thresholds, pricing and expose safe diagnostics',async({page})=>{
  await page.goto('/settings');await page.getByRole('button',{name:'Light',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await page.locator('#threshold_tokens').fill('1234567');await page.getByRole('button',{name:'Save usage preferences'}).click();await expect(page.getByRole('status').filter({hasText:'Preferences saved'})).toBeVisible();
  await page.getByRole('button',{name:'Show details'}).click();await expect(page.getByText('rollout-v1 / v1',{exact:true})).toBeVisible();
  await page.locator('#time-format').selectOption('utc');await page.goto('/tasks?range=all');await expect(page.locator('.task-link').first()).toContainText('UTC');await page.goto('/settings');
  await page.getByRole('button',{name:'Dark',exact:true}).click();
});
test('CSV export downloads safe normalized data',async({page})=>{
  await page.goto('/tasks?range=all');const download=page.waitForEvent('download');await page.getByRole('link',{name:'Export CSV'}).click();
  const file=await download;expect(file.suggestedFilename()).toBe('tasks.csv');
  const stream=await file.createReadStream();let text='';for await(const chunk of stream!)text+=chunk.toString();
  expect(text).toContain('uncached_input_tokens');expect(text).not.toContain('PRIVATE');
});
test('API failure, reconnect and narrow keyboard navigation',async({page})=>{
  await page.route('**/api/analytics?*',route=>route.fulfill({status:503,body:'{}'}));await page.goto('/');await expect(page.getByRole('alert')).toContainText('Unable to load local data');
  await page.unroute('**/api/analytics?*');await page.getByRole('button',{name:'Try again'}).click();await expect(page.getByText('Turn trace',{exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Open navigation'}).click();await page.getByRole('navigation').getByRole('link',{name:'Tasks',exact:true}).click();await expect(page).toHaveURL(/tasks/);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.keyboard.press('Tab');await expect(page.locator(':focus')).not.toHaveCount(0);
});
test('live updates and idle state use backend lifecycle',async({page,request})=>{
  await page.goto('/live');await expect(page.locator('.activity-top')).toContainText('CURRENT ACTIVITY');
  const {appendFile}=await import('node:fs/promises');
  const now=new Date().toISOString();
  const usage={input_tokens:100,cached_input_tokens:60,cache_write_input_tokens:0,output_tokens:20,reasoning_output_tokens:5,total_tokens:120};
  const cumulative={input_tokens:10100,cached_input_tokens:5060,cache_write_input_tokens:0,output_tokens:220,reasoning_output_tokens:55,total_tokens:10320};
  await appendFile('.local/e2e/sessions/0.jsonl',JSON.stringify({timestamp:now,type:'token_usage_record',payload:{response_id:'qa-live-append',thread_id:'qa-thread-0',session_id:'qa-thread-0',turn_id:'turn-a',root_turn_id:'root-turn',usage,turn_token_usage:cumulative,thread_token_usage:cumulative}})+'\n');
  await expect(page.locator('.big-number')).toContainText('10,320',{timeout:10000});
  await appendFile('.local/e2e/sessions/0.jsonl',JSON.stringify({timestamp:now,type:'event_msg',payload:{type:'task_complete',turn_id:'turn-a'}})+'\n');
  await expect(page.locator('.activity-top')).toContainText('CODEX IS IDLE',{timeout:10000});
  await expect(page.locator('.activity-secondary')).toContainText('Latest recorded turn');
});
