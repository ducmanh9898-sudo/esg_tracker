const {chromium}=require('playwright');
const assert=require('assert/strict');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.goto(process.env.ESG_UI_URL || 'http://127.0.0.1:8051/',{waitUntil:'domcontentloaded'});
    await page.locator('#analysis-history-note').filter({hasText:'lần trích xuất đã lưu'}).waitFor({timeout:120000});
    const count=await page.locator('#analysis-history-note').innerText();
    await page.locator('#analysis-history input').focus();
    await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
    await page.locator('#analysis-history-open').click();
    await page.locator('#analysis-history-feedback').filter({hasText:'Đã mở kết quả'}).waitFor({timeout:120000});
    await page.locator('#analysis-download-button:not([disabled])').waitFor({timeout:120000});
    const downloadPromise=page.waitForEvent('download',{timeout:120000});
    await page.locator('#analysis-download-button').click();
    const download=await downloadPromise;
    assert(download.suggestedFilename().endsWith('.json'));
    // A new browser context has no session store or cached job: discover again from disk.
    const fresh=await browser.newPage();
    await fresh.goto('http://127.0.0.1:8051/',{waitUntil:'domcontentloaded'});
    await fresh.locator('#analysis-history-note').filter({hasText:'lần trích xuất đã lưu'}).waitFor({timeout:120000});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,count,download:download.suggestedFilename(),newSession:true,mobile:true,errors}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
