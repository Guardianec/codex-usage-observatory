import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const browser=await chromium.launch();
const page=await browser.newPage({viewport:{width:1440,height:900}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await mkdir('.local/screenshots',{recursive:true});
const base='http://127.0.0.1:8765';
await page.goto(base+'/');await page.getByText('Turn trace',{exact:true}).waitFor();
const firstTask=await page.locator('.task-link').first().getAttribute('href');
const reports=[];
for(const [width,height] of [[1440,900],[1280,800],[1024,768]]){
  await page.setViewportSize({width,height});
  for(const [name,route,ready] of [['overview','/','Turn trace'],['live','/live','Live trace'],['tasks','/tasks','Recorded turns'],['task-detail',firstTask,'Model responses'],['models','/models','Model statistics'],['settings','/settings','Appearance']]){
    await page.goto(base+route);await page.getByRole('heading',{name:ready,exact:true}).waitFor();await page.evaluate(()=>document.fonts.ready);
    await page.screenshot({path:`.local/screenshots/${name}-${width}.png`,fullPage:true,animations:'disabled'});
    reports.push({page:name,width,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});
  }
}
await page.setViewportSize({width:1440,height:900});await page.goto(base+'/settings');await page.getByRole('button',{name:'Light',exact:true}).click();
await page.screenshot({path:'.local/screenshots/settings-light.png',fullPage:true,animations:'disabled'});await page.goto(base+'/');await page.getByText('Turn trace',{exact:true}).waitFor();await page.screenshot({path:'.local/screenshots/overview-light.png',fullPage:true,animations:'disabled'});
await page.goto(base+'/settings');await page.getByRole('button',{name:'Dark',exact:true}).click();
await page.setViewportSize({width:390,height:844});await page.goto(base+'/');await page.getByText('Turn trace',{exact:true}).waitFor();await page.screenshot({path:'.local/screenshots/overview-390.png',fullPage:true,animations:'disabled'});
reports.push({page:'overview',width:390,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});
await writeFile('.local/visual-report.json',JSON.stringify({errors,reports},null,2));
console.log(JSON.stringify({errors,reports},null,2));
await browser.close();
