const {chromium}=require('playwright');
const assert=require('assert/strict');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.goto('http://127.0.0.1:8051/',{waitUntil:'domcontentloaded'});
    await page.locator('#analysis-history-note').filter({hasText:'lần trích xuất đã lưu'}).waitFor({timeout:120000});
    await page.locator('#analysis-history input').fill('BCTC_BSR_2024.pdf');
    await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
    await page.locator('#analysis-history-open').click();
    await page.locator('#analysis-handoff-button:not([disabled])').waitFor({timeout:120000});
    const downloadPromise=page.waitForEvent('download',{timeout:240000});
    await page.locator('#analysis-handoff-button').click();
    const download=await downloadPromise;
    assert(download.suggestedFilename().endsWith('.zip'));
    assert.equal(await download.failure(),null);
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,filename:download.suggestedFilename(),status:await page.locator('#analysis-handoff-status').innerText(),errors}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
