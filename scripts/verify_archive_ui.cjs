/* Archived dashboard theme and existing interactions, against the local app. */
const {chromium} = require('playwright');
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
(async () => {
  const out = path.resolve('outputs/ui_qa_20261011/archive');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({channel:'msedge', headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const results = [];
  try {
    await page.goto('http://127.0.0.1:8050/', {waitUntil:'networkidle'});
    const archive = page.locator('.legacy-dashboard');
    await archive.locator('summary').click();
    await page.locator('#k-claims').filter({hasText:/\d/}).waitFor();
    const initialCount = await page.locator('#k-claims').innerText();
    await page.locator('#reset').click();
    assert.equal(await page.locator('#k-claims').innerText(), initialCount);
    const tabs = archive.locator('.custom-tab');
    assert.equal(await tabs.count(), 5);
    for (const [name,width,height] of [['desktop',1440,1000],['tablet',1024,900],['mobile',390,844],['small-mobile',320,740]]) {
      await page.setViewportSize({width,height});
      for (let index=0; index<5; index++) {
        await tabs.nth(index).click();
        await page.waitForTimeout(400);
        const sizes = await page.evaluate(() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
        assert(sizes.scroll <= sizes.client+1, `${name} tab ${index} overflows: ${JSON.stringify(sizes)}`);
        const style = await archive.locator('.custom-tab--selected').evaluate(el => {
          const s=getComputedStyle(el); return {color:s.color,background:s.backgroundColor,image:s.backgroundImage};
        });
        assert.equal(style.color,'rgb(20, 83, 45)');
        assert.equal(style.background,'rgb(240, 253, 244)');
        assert.equal(style.image,'none');
        if (index===4) await page.locator('#viewer-detail .detail-card').first().waitFor();
        results.push({name,tab:index,...sizes,style});
      }
      await archive.scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(out,`${name}-evidence.png`),fullPage:true});
      await tabs.nth(0).click();
      await page.locator('#top-claims td.dash-cell').first().waitFor();
      await page.screenshot({path:path.join(out,`${name}-overview.png`),fullPage:true});
      await archive.locator('.header').evaluate(el=>el.scrollIntoView({block:'start'}));
      await page.screenshot({path:path.join(out,`${name}-archive-viewport.png`)});
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#reset').focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement.id), 'reset');
    assert.notEqual(await page.locator('#reset').evaluate(el=>getComputedStyle(el).outlineStyle),'none');
    assert.equal(await page.locator('#k-claims').innerText(), initialCount);
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({initialCount,results,errors},null,2));
    console.log(JSON.stringify({passed:true,layouts:results.length,initialCount,errors,out}));
  } finally { await browser.close(); }
})().catch(e=>{ console.error(e); process.exitCode=1; });
