const {chromium}=require('playwright');
const fs=require('fs'),http=require('http'),assert=require('assert'),path=require('path');
(async()=>{
const root=path.join(__dirname,'../web');
const screenshots=path.join(__dirname,'../ui-checks');fs.mkdirSync(screenshots,{recursive:true});
const server=http.createServer((req,res)=>{if(req.url==='/heartbeat'){res.setHeader('Content-Type','application/json');return res.end('{"ok":true}')}const name=req.url==='/'?'index.html':req.url.slice(1);res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');const file=path.join(root,name);if(!fs.existsSync(file)){res.statusCode=404;return res.end()}res.end(fs.readFileSync(file));});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try{
const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(`http://127.0.0.1:${server.address().port}/`);
for(const screen of ['databaseScreen','mainScreen','roomMapScreen','seatingScreen']){
 await page.evaluate(id=>document.querySelectorAll('main').forEach(e=>e.hidden=e.id!==id),screen);
 assert(await page.locator('#about').isVisible());
 assert(!(await page.locator('body').innerText()).includes('18.0.0'));
 assert(!(await page.locator('body').innerText()).includes('אסי וינברגר'));
 await page.locator('#about').click();assert(await page.locator('#aboutDialog').isVisible());
 assert((await page.locator('#aboutDialog').innerText()).includes('18.0.0'));
 assert((await page.locator('#aboutDialog').innerText()).includes('אסי וינברגר ואייל שיף'));
 await page.keyboard.press('Escape');assert(!(await page.locator('#aboutDialog').isVisible()));assert(await page.locator('#about').evaluate(e=>e===document.activeElement));
}
await page.evaluate(()=>document.querySelectorAll('main').forEach(e=>e.hidden=e.id!=='databaseScreen'));
await page.screenshot({path:path.join(screenshots,'v18-main.png'),fullPage:true});
await page.locator('#about').click();await page.screenshot({path:path.join(screenshots,'v18-about.png')});
await page.locator('#closeAbout').click();assert(!(await page.locator('#aboutDialog').isVisible()));
await page.locator('#about').click();await page.mouse.click(5,5);assert(!(await page.locator('#aboutDialog').isVisible()));
await page.locator('#skipDatabase').click();assert(await page.locator('#mainScreen').isVisible());await page.locator('input[name=grade][value="י׳"]').check();assert(await page.locator('#chooseClasslist').isEnabled());
await page.setViewportSize({width:390,height:844});await page.locator('#about').click();
const b=await page.locator('#aboutDialog').boundingBox();assert(b.x>=0&&b.x+b.width<=390);assert(await page.locator('#closeAbout').isVisible());
await page.screenshot({path:path.join(screenshots,'v18-about-mobile.png')});
assert.deepStrictEqual(errors,[]);console.log('About checks passed: four screens, hidden credits/version, Escape, close, backdrop, focus restoration, workflow controls, narrow viewport, no JS errors');
}finally{await browser.close();server.close()}
})().catch(e=>{console.error(e);process.exit(1)});
