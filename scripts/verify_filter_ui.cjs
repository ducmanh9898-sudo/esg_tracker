const {chromium}=require('playwright');
const assert=require('assert/strict');
const fs=require('fs');
const path=require('path');
(async()=>{
  const out=path.resolve('outputs/ui_qa_20261011/filters');
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.goto(process.env.ESG_UI_URL || 'http://127.0.0.1:8050/',{waitUntil:'networkidle'});
    await page.locator('.legacy-dashboard summary').click();
    for (const width of [1440,1024,390,320]) {
      await page.setViewportSize({width,height:1000});
      const input=page.locator('#f-metric input[role=combobox]');
      await input.focus();
      await page.keyboard.type('năng lượng');
      await page.locator('#f-metric .VirtualizedSelectOption').filter({hasText:'Tổng năng lượng'}).waitFor();
      const focus=await input.evaluate(el=>({outline:getComputedStyle(el).outlineStyle,border:getComputedStyle(el).borderWidth}));
      assert.equal(focus.outline,'none');
      assert.equal(focus.border,'0px');
      assert.notEqual(await page.locator('#f-metric .Select-control').evaluate(el=>getComputedStyle(el).boxShadow),'none');
      await page.locator('.legacy-dashboard .filters').screenshot({path:path.join(out,`options-${width}.png`)});
      await page.keyboard.press('Enter');
      await page.locator('#f-metric .Select-value-label').filter({hasText:'Tổng năng lượng'}).waitFor();
      assert.equal(await page.locator('#f-metric .Select-value').evaluate(el=>getComputedStyle(el).lineHeight),'20px');
      await page.locator('.legacy-dashboard .filters').screenshot({path:path.join(out,`selected-${width}.png`)});
      const fits=await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1);
      assert(fits, `overflow at ${width}`);
      await page.locator('#f-metric .Select-value-icon').click();
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#f-metric .Select-value').count(),0);
    }
    await page.locator('#f-mode input[role=combobox]').focus();
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('#f-mode input[role=combobox]').evaluate(el=>getComputedStyle(el).outlineStyle),'none');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,widths:[1440,1024,390,320],keyboardSelection:true,chipRemoval:true,errors}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
