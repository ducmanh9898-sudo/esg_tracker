/* Local real-browser UI regression; extraction optional via --extract. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');

function contrast(a,b) {
  const lum = hex => {
    const rgb = hex.replace('#','').match(/../g).map(x => parseInt(x,16)/255).map(x => x <= .04045 ? x/12.92 : ((x+.055)/1.055)**2.4);
    return rgb[0]*.2126 + rgb[1]*.7152 + rgb[2]*.0722;
  };
  const aa=lum(a), bb=lum(b); return (Math.max(aa,bb)+.05)/(Math.min(aa,bb)+.05);
}
(async () => {
  const out = path.resolve('outputs/ui_qa_20261011');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true, channel:process.env.ESG_UI_BROWSER || 'msedge'});
  const page = await browser.newPage({viewport:{width:1440,height:1000}, reducedMotion:'reduce'});
  const errors=[];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto('http://127.0.0.1:8050', {waitUntil:'networkidle'});
    await page.locator('#ui-table-empty').getByText('Báo cáo đầu tiên bắt đầu ở đây').waitFor();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement.className),'skip-link');
    await page.evaluate(()=>document.activeElement.blur());
    assert.equal(await page.locator('#ui-claim-count').innerText(), '—');
    await page.screenshot({path:path.join(out,'desktop-top.png')});
    await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
    const viewports=[];
    for (const [name,width,height] of [['tablet',1024,900],['mobile',390,844],['small-mobile',320,740]]) {
      await page.setViewportSize({width,height});
      await page.waitForTimeout(200);
      const sizes=await page.evaluate(() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
      assert(sizes.scroll <= sizes.client+1, `${name} body overflows: ${JSON.stringify(sizes)}`);
      await page.screenshot({path:path.join(out,`${name}.png`),fullPage:true});
      viewports.push({name,width,...sizes});
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#analysis-start').click();
    await page.locator('.extract-status--error').waitFor();
    await page.locator('#ui-retry').waitFor({state:'visible'});
    await page.locator('#ui-retry').click();
    await page.locator('#ui-retry-feedback').getByText('Đã yêu cầu thử lại').waitFor();
    await page.locator('.workspace-nav-link[href="#claims"]').click();
    assert.equal(await page.evaluate(() => location.hash), '#claims');
    await page.locator('#ui-search').focus();
    const focus=await page.locator('#ui-search').evaluate(el => getComputedStyle(el).outlineStyle);
    assert.notEqual(focus,'none');
    await page.locator('#ui-search').fill('không có dữ liệu');
    await page.locator('#ui-search').blur();
    const ratios=[['text','#172B22','#FFFFFF'],['muted','#64746B','#FFFFFF'],['muted-light','#64746B','#F0FDF4'],
                  ['primary','#FFFFFF','#15803D'],['warning','#92400E','#FFFBEB'],['error','#991B1B','#FEF2F2']]
      .map(([name,a,b])=>({name,ratio:contrast(a,b)}));
    ratios.forEach(item=>assert(item.ratio>=4.5,`${item.name} fails AA: ${item.ratio}`));
    const placeholder = await page.locator('#ui-company .Select-placeholder').evaluate(el=>getComputedStyle(el).color);
    assert.equal(placeholder,'rgb(100, 116, 107)'); // Actual cascade, not just token values.
    assert.equal(await page.locator('#ui-company input').getAttribute('aria-label'),'Doanh nghiệp');
    let extraction=null;
    if (process.argv.includes('--extract')) {
      await page.locator('#ui-search').fill('');
      await page.locator('#ui-search').blur();
      await page.locator('#analysis-upload input[type=file]').setInputFiles('C:/Users/THINKPAD/Documents/esg/data/raw_pdf/BCTC/BCTC_BSR_2024.pdf');
      await page.locator('#analysis-company').fill('BSR');
      await page.locator('#analysis-year').fill('2024');
      // Keep auto number format; this UI check must not override financial conventions.
      await page.locator('#analysis-start').click();
      await page.locator('.extract-status--running').waitFor({timeout:20000});
      await page.locator('.extract-status--completed').waitFor({timeout:180000});
      assert.equal(await page.locator('#ui-report-count').innerText(),'1');
      assert.equal(await page.locator('#ui-claim-count').innerText(),'0'); // Financial metrics are NOT claims.
      await page.locator('#ui-year .Select-control').click();
      await page.locator('.VirtualizedSelectOption, .Select-option').filter({hasText:'2024'}).click();
      await page.locator('#ui-table-summary').filter({hasText:'record'}).waitFor();
      assert.equal(await page.locator('#ui-table-empty').innerText(),'');
      await page.locator('#ui-company .Select-control').click();
      await page.locator('.VirtualizedSelectOption, .Select-option').filter({hasText:'BSR'}).click();
      await page.locator('#ui-table-summary').filter({hasText:'record'}).waitFor();
      assert.equal(await page.locator('#ui-table-empty').innerText(),'');
      await page.locator('#analysis-records input[type=radio]').first().check();
      await page.locator('#analysis-source-detail .claim-quote').waitFor();
      await page.locator('#analysis-source-link:not([hidden])').waitFor();
      const href=await page.locator('#analysis-source-link').getAttribute('href');
      const response=await page.request.get(new URL(href.split('#')[0], 'http://127.0.0.1:8050').href);
      assert.equal(response.status(),200);
      const downloadPromise=page.waitForEvent('download');
      await page.locator('#analysis-download-button').click();
      const download=await downloadPromise;
      assert(download.suggestedFilename().endsWith('.json'));
      extraction={status:await page.locator('#analysis-status').innerText(),filename:download.suggestedFilename(),pdf_status:response.status()};
      await page.locator('#ui-search').fill('ZZZ_NO_MATCH_20261011');
      await page.locator('#ui-search').blur();
      await page.locator('#ui-table-empty').getByText('Không có kết quả phù hợp').waitFor();
      await page.locator('#ui-search').fill('');
      await page.locator('#ui-search').blur();
      await page.locator('#ui-review .Select-control').click();
      await page.locator('.VirtualizedSelectOption, .Select-option').filter({hasText:'Đã rà soát (có trạng thái lưu)'}).click();
      await page.locator('#ui-table-empty').getByText('Không có kết quả phù hợp').waitFor();
      await page.locator('#ui-review .Select-clear-zone').click();
      await page.setViewportSize({width:390,height:844});
      await page.screenshot({path:path.join(out,'mobile-results.png'),fullPage:true});
      const sizes=await page.evaluate(() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
      assert(sizes.scroll<=sizes.client+1,'Result view overflows mobile');
    }
    assert.deepEqual(errors,[]);
    const report={viewports,contrast:ratios,keyboard_focus:focus,retry:true,navigation:true,extraction,console_errors:errors};
    fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
