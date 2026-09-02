// Render the prospectus HTML to a Letter-size PDF with headless Chromium.
//   node reports/prospectus/render_pdf.cjs <in.html> <out.pdf>
// Requires the playwright package (npm i -g playwright) and a Chromium build;
// set CHROMIUM_PATH to point at a specific binary, otherwise Playwright's own
// download is used.
const path = require('path');
const fs = require('fs');

function loadPlaywright() {
  try { return require('playwright'); } catch (e) { /* fall through */ }
  const globalRoot = require('child_process').execSync('npm root -g').toString().trim();
  return require(path.join(globalRoot, 'playwright'));
}

(async () => {
  const [inHtml, outPdf] = process.argv.slice(2);
  if (!inHtml || !outPdf) { console.error('usage: render_pdf.cjs <in.html> <out.pdf>'); process.exit(2); }
  const { chromium } = loadPlaywright();
  const launch = {};
  if (process.env.CHROMIUM_PATH) launch.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(launch);
  const page = await browser.newPage();
  await page.emulateMedia({ media: 'print' });
  await page.goto('file://' + path.resolve(inHtml), { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const stamp = new Date().toISOString().slice(0, 10);
  const foot = (align) => `<div style="font-family:'Libre Franklin',Helvetica,Arial,sans-serif;font-size:7px;letter-spacing:0.08em;text-transform:uppercase;color:#7C8794;width:100%;padding:0 0.8in;display:flex;justify-content:space-between;">
      <span>The Signal · Confidential investment prospectus</span><span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`;
  await page.pdf({
    path: outPdf, format: 'Letter', printBackground: true, preferCSSPageSize: false,
    displayHeaderFooter: true, headerTemplate: '<div></div>', footerTemplate: foot(),
    margin: { top: '0.7in', bottom: '0.75in', left: '0.8in', right: '0.8in' },
  });
  await browser.close();
  console.log('rendered', outPdf, fs.statSync(outPdf).size, 'bytes', stamp);
})().catch((e) => { console.error(e); process.exit(1); });
