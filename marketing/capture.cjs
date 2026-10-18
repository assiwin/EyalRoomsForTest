const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),{spawn}=require('child_process');
const out=path.resolve('marketing/capture');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const child=spawn('python',['-u','app.py','--no-browser'],{stdio:['ignore','pipe','pipe']});
 let log='';child.stderr.on('data',x=>{log+=x.toString()});
 const url=await new Promise((resolve,reject)=>{child.stdout.on('data',x=>{const m=x.toString().match(/http:\/\/127\.0\.0\.1:\d+\//);if(m)resolve(m[0])});child.on('exit',c=>reject(Error('app exited '+c+' '+log)));setTimeout(()=>reject(Error('No app URL '+log)),30000)});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext({viewport:{width:1600,height:900},deviceScaleFactor:1,recordVideo:{dir:path.join(out,'raw-video'),size:{width:1600,height:900}}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);await page.waitForTimeout(1000);
  await page.screenshot({path:path.join(out,'01-database.png')});
  await page.locator('#skipDatabase').click();await page.locator('input[name=grade][value="י״א"]').check();
  await page.screenshot({path:path.join(out,'02-dashboard.png')});
  await page.route('**/select-classlist',async route=>{
   const response=await page.request.post(url+'upload',{headers:{'X-App-Token':await page.locator('meta[name=app-token]').getAttribute('content'),'X-Filename':'demo_classlist.xlsx'},data:fs.readFileSync(path.join(out,'demo_classlist.xlsx'))});
   if(!response.ok())throw Error(await response.text());
   await route.fulfill({status:200,contentType:'application/json',body:await response.text()});
  });
  await page.locator('#chooseClasslist').click();await page.locator('input[name=reducedRooms][value="1"]').check();
  await page.locator('#run').scrollIntoViewIfNeeded();await page.waitForTimeout(1000);
  await page.screenshot({path:path.join(out,'03-settings.png')});
  await page.locator('#run').click();await page.waitForFunction(()=>document.querySelector('#results .summary'),{},{timeout:150000});
  await page.locator('#results').scrollIntoViewIfNeeded();await page.waitForTimeout(1200);
  await page.screenshot({path:path.join(out,'04-results.png')});
  await page.locator('#results').screenshot({path:path.join(out,'results-element.png')});
  await page.locator('#adjust').scrollIntoViewIfNeeded();await page.waitForTimeout(500);await page.screenshot({path:path.join(out,'05-adjust.png')});
  await page.locator('#makeMatrixPdf').click();await page.locator('#matrixPdfSuccess').waitFor({state:'visible'});
  await page.locator('#makePdf').click();await page.locator('#pdfSuccess').waitFor({state:'visible'});
  await page.locator('#next').click();await page.waitForTimeout(700);
  const inputs=await page.locator('.physical-room').all();for(let i=0;i<inputs.length;i++)await inputs[i].fill(String(101+i));
  await page.screenshot({path:path.join(out,'06-roommap.png')});
  await page.locator('#makeTeacherReports').click();await page.locator('#teacherReportsSuccess').waitFor({state:'visible'});
  await page.locator('#teacherReportsSuccess').scrollIntoViewIfNeeded();await page.waitForTimeout(700);
  await page.screenshot({path:path.join(out,'07-reports.png')});
  await page.locator('#nextToSeating').click();await page.locator('#makeSeatingPlans').click();await page.locator('#seatingSuccess').waitFor({state:'visible'});
  await page.waitForTimeout(1300);await page.screenshot({path:path.join(out,'08-seating.png')});
  const meta=await page.evaluate(()=>({students:result.participants,rooms:result.total,regular:result.regular,special:result.special,dedicated:result.dedicated,teachers:result.matrix.rows.length}));
  fs.writeFileSync(path.join(out,'demo-meta.json'),JSON.stringify({...meta,errors},null,2));
  if(errors.length)throw Error(errors.join('\n'));
  fs.copyFileSync('assets/app_icon.png',path.join(out,'app_icon.png'));
  for(const file of fs.readdirSync('Output'))if(file.endsWith('.pdf'))fs.copyFileSync(path.join('Output',file),path.join(out,file));
  console.log('CAPTURE SUCCESS',meta);
 }finally{await context.close();await browser.close();child.kill();}
})().catch(e=>{console.error(e);process.exit(1)});
