const $=id=>document.getElementById(id),token=document.querySelector('meta[name=app-token]').content;
let loaded=false,busy=false,pdfBusy=false,matrixPdfBusy=false,schedulePdfBusy=false,teacherReportsBusy=false,filename='',baseTotal=null,result=null,pollTimer=null,uploadEpoch=0,pdfInfo=null,matrixPdfInfo=null,teacherReportsInfo=null,examSchedule=null,appLocked=false,savedRoomLabels={};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const scheduleLevels=['3a','3','4','5'],scheduleExtras=[0,25,33,50];
const scheduleDefaults={'3a':{start:'10:25',duration:100},3:{start:'08:45',duration:100},4:{start:'08:45',duration:160},5:{start:'10:35',duration:130}};
function scheduleEnd(start,duration,extra){
  if(!/^\d{2}:\d{2}$/.test(start)||!Number.isInteger(duration)||duration<1)return '—';
  const [hours,minutes]=start.split(':').map(Number),total=hours*60+minutes+duration+Math.floor(duration*extra/100);
  return String(Math.floor(total/60)%24).padStart(2,'0')+':'+String(total%60).padStart(2,'0');
}
function readSchedule(){
  const value={};
  for(const level of scheduleLevels)value[level]={start:$('start-'+level).value,duration:Number($('duration-'+level).value)};
  return value;
}
function applySchedule(value){
  for(const level of scheduleLevels){const row=value?.[level]||scheduleDefaults[level];$('start-'+level).value=row.start;$('duration-'+level).value=row.duration}
  updateSchedule();
}
function updateSchedule(){
  const value=readSchedule(),valid=$('scheduleForm').checkValidity();
  for(const level of scheduleLevels)for(const extra of scheduleExtras)$('end-'+level+'-'+extra).textContent=scheduleEnd(value[level].start,value[level].duration,extra);
  examSchedule=valid?value:null;
  if(valid){localStorage.setItem('exam-room-schedule-v8',JSON.stringify(value));$('scheduleSaveStatus').textContent='הזמנים נשמרו במחשב.'}
  else $('scheduleSaveStatus').textContent='יש להשלים שעת התחלה ומשך תקינים לכל רמה.';
  controls();
}
$('scheduleForm').oninput=updateSchedule;
$('resetSchedule').onclick=()=>{localStorage.removeItem('exam-room-schedule-v8');applySchedule(scheduleDefaults)};
$('makeSchedulePdf').onclick=async()=>{
  if(!$('scheduleForm').reportValidity())return;
  try{schedulePdfBusy=true;controls();$('scheduleSaveStatus').textContent='מפיק PDF של זמני הבחינה…';const info=await api('/schedule-pdf',{schedule:readSchedule()});$('scheduleSaveStatus').textContent=`נוצר ${info.filename}. תיקיית הפלט נפתחה.`}
  catch(e){error(e.message);$('scheduleSaveStatus').textContent='הפקת קובץ זמני הבחינה נכשלה.'}
  finally{schedulePdfBusy=false;controls()}
};
try{applySchedule(JSON.parse(localStorage.getItem('exam-room-schedule-v8'))||scheduleDefaults)}catch{applySchedule(scheduleDefaults)}

async function api(path,body,raw=false){
  const headers={'X-App-Token':token};
  if(raw)headers['X-Filename']=encodeURIComponent(filename);else headers['Content-Type']='application/json';
  const r=await fetch(path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:raw?body:JSON.stringify(body)});
  if(!r.ok){let message='הפעולה נכשלה';try{message=(await r.json()).error||message}catch{}throw Error(message)}
  return ['/download','/download-pdf','/download-matrix-pdf','/download-teacher-reports','/download-reading-list'].includes(path)?r.blob():r.json();
}
function error(s){$('error').hidden=!s;$('error').textContent=s||''}
function cfg(){const c={special:{},singleDesk:$('singleDesk').value==='yes'};for(const k of ['normal','maximum','percent','level','limit'])c[k]=Number($(k).value);document.querySelectorAll('[data-special]').forEach(e=>c.special[e.dataset.special]=Number(e.value));return c}
function selectedGrade(){return document.querySelector('input[name=grade]:checked')?.value||''}
function updateGradeDisplay(){$('selectedGradeDisplay').textContent=selectedGrade()||'טרם נבחרה'}
function noteRows(){return [...document.querySelectorAll('.note-row')]}
function noteValid(){return noteRows().every(row=>{const room=row.querySelector('.note-room').value,text=row.querySelector('.note-text').value.trim();return (!room&&!text)||(room&&text&&text.length<=120)})}
function invalidatePdf(){pdfInfo=null;$('pdfSuccess').hidden=true;$('pdfStatus').textContent='';envelopeControls()}
function invalidateMatrixPdf(){matrixPdfInfo=null;$('matrixPdfSuccess').hidden=true;$('matrixPdfStatus').textContent=''}
function invalidateTeacherReports(){teacherReportsInfo=null;$('teacherReportsSuccess').hidden=true;$('teacherReportsStatus').textContent='';$('teacherFileList').textContent=''}
function envelopeControls(){
  const available=!!result;$('envelopeSection').hidden=!available;
  $('makePdf').disabled=busy||pdfBusy||appLocked||!available||!selectedGrade()||!noteValid();
  document.querySelectorAll('#envelopeSection input,#envelopeSection select').forEach(e=>e.disabled=busy||pdfBusy||appLocked);
  document.querySelectorAll('#envelopeSection button').forEach(e=>{if(!['makePdf','addNote'].includes(e.id))e.disabled=busy||pdfBusy});
  $('addNote').disabled=busy||pdfBusy||appLocked||noteRows().length>=2;
}
function controls(){
  const scheduleValid=$('scheduleForm').checkValidity(),valid=loaded&&scheduleValid&&$('settings').checkValidity()&&Number($('normal').value)<=Number($('maximum').value);
  $('run').disabled=busy||!valid||appLocked;$('cancel').hidden=!busy;$('settings').querySelectorAll('input,select').forEach(e=>e.disabled=busy||appLocked);$('file').disabled=busy||!scheduleValid;$('makeSchedulePdf').disabled=busy||schedulePdfBusy||!scheduleValid;
  $('download').disabled=busy;$('report').disabled=busy;$('reset').disabled=busy;$('next').disabled=busy||!pdfInfo;$('nextHelp').hidden=!result||!!pdfInfo;target();envelopeControls();
}
function target(){const n=Number($('delta').value),sign=document.querySelector('input[name=op]:checked').value==='add'?1:-1;const t=baseTotal+sign*n;$('target').textContent=baseTotal?`בסיס: ${baseTotal} חדרים · יעד מבוקש: ${t}`:'';$('rebalance').disabled=busy||!baseTotal||!Number.isInteger(n)||n<1||t<1||t>Number($('limit').value)}

async function upload(file){
  if(!file||busy)return;const epoch=++uploadEpoch;clearTimeout(pollTimer);loaded=false;result=null;baseTotal=null;invalidatePdf();invalidateMatrixPdf();invalidateTeacherReports();render();error('');filename=file.name;controls();$('status').textContent='קורא ובודק את הקובץ…';
  try{const b=await api('/upload',await file.arrayBuffer(),true);if(epoch!==uploadEpoch)return;loaded=true;appLocked=!!b.management?.locked;savedRoomLabels=b.management?.roomLabels||{};$('unlockWrap').hidden=!appLocked;$('unlock').checked=false;$('lockNotice').hidden=!appLocked;document.body.classList.toggle('app-locked',appLocked);$('fileinfo').innerHTML=`<b dir="ltr">${esc(filename)}</b><p>${b.records} רשומות · ${b.participants} משתתפים · ${b.records-b.participants} לא משתתפים</p>`;$('special').innerHTML=Object.entries(b.special).map(([k,n])=>`<div class="info"><b>${{K:'מצומצם 1',L:'מצומצם 2',M:'נפרד'}[k]}: ${n} תלמידים</b><div class="field"><label for="cap-${k}">קיבולת מאושרת לחדר</label><input id="cap-${k}" data-special="${k}" type="number" min="${n}" max="1000" required placeholder="—"></div><p class="note">לא יתבצע פיצול אוטומטי. הזינו רק קיבולת מאושרת.</p></div>`).join('');if(b.restoredResult){result=b.restoredResult;baseTotal=b.baseTotal||result.total;pdfInfo={restored:true};if(b.grade){const grade=document.querySelector(`input[name=grade][value="${CSS.escape(b.grade)}"]`);if(grade)grade.checked=true}const settings=result.settings||{};for(const key of ['normal','maximum','percent','level','limit'])if(Number.isFinite(settings[key]))$(key).value=settings[key];$('singleDesk').value=settings.singleDesk?'yes':'no';for(const [key,value] of Object.entries(settings.special||{})){const input=$('cap-'+key);if(input)input.value=value}updateGradeDisplay();updateSingleDeskInfo();render()}$('status').textContent=b.restoredResult?'הקובץ נטען במצב נעול וכל תוצאות השיבוץ שוחזרו.':appLocked?'הקובץ נטען במצב נעול, אך לא נמצאה תוצאת שיבוץ שמורה מגרסה קודמת.':Object.keys(b.special).length?'הקובץ תקין. יש להזין קיבולת מאושרת לחדרים המיוחדים.':'הקובץ תקין ומוכן לחישוב.'}
  catch(e){error(e.message);$('fileinfo').textContent='';$('special').innerHTML='';$('status').textContent='לא נטען קובץ תקין.'}controls();
}
$('file').onchange=e=>upload(e.target.files[0]);$('drop').ondragover=e=>e.preventDefault();$('drop').ondrop=e=>{e.preventDefault();upload(e.dataTransfer.files[0])};
function updateSingleDeskInfo(){$('singleDeskInfo').hidden=$('singleDesk').value!=='yes'}
$('settings').oninput=async()=>{updateSingleDeskInfo();clearTimeout(pollTimer);result=null;baseTotal=null;invalidatePdf();invalidateMatrixPdf();invalidateTeacherReports();render();controls();try{await api('/invalidate',{})}catch(e){error(e.message)}};

async function run(mode){if(!$('settings').reportValidity())return;busy=true;invalidatePdf();invalidateMatrixPdf();invalidateTeacherReports();controls();error('');$('status').textContent='מחפש שיבוץ תקין ומאזן חדרים. ניתן לבטל. החיפוש מוגבל בזמן.';try{await api('/run',{settings:cfg(),mode,delta:Number($('delta').value),op:document.querySelector('input[name=op]:checked').value});poll()}catch(e){busy=false;error(e.message);controls()}}
async function poll(){try{const s=await api('/status');busy=s.busy;if(busy){pollTimer=setTimeout(poll,700);return}result=s.result;baseTotal=s.baseTotal;invalidatePdf();invalidateMatrixPdf();invalidateTeacherReports();render();error(s.error);$('status').textContent=s.error?(result?'הניסיון לא הצליח. התוצאה התקינה הקודמת זמינה להורדה.':'לא נוצר שיבוץ.'):result?'החישוב הסתיים והקובץ עבר בדיקת שמירה.':'החישוב בוטל.';controls()}catch(e){busy=false;error(e.message);controls()}}

function matrix(r){const over=new Set(r.rooms.filter(x=>x.overflow).map(x=>x.room));return `<section class="matrix-section"><h3>מטריצת מורים וחדרים</h3><p class="note">בכל תא מוצג מספר התלמידים של המורה ורמת הלימוד ששובצו לחדר. ניתן לגלול לצדדים.</p><div class="matrixwrap"><table class="matrix"><thead><tr><th class="sticky-name">שם מורה</th><th class="sticky-unit">יחידות</th><th class="sticky-total">סה״כ</th>${r.matrix.rooms.map(n=>`<th class="${over.has(n)?'over':''}">${n}</th>`).join('')}<th>בדיקה</th></tr></thead><tbody>${r.matrix.rows.map(x=>`<tr><th class="sticky-name">${esc(x.teacher)}</th><td class="sticky-unit">${esc(x.unit)}</td><td class="sticky-total total">${x.total}</td>${x.counts.map(n=>`<td>${n||''}</td>`).join('')}<td class="check">${x.total-x.counts.reduce((a,b)=>a+b,0)}</td></tr>`).join('')}<tr class="grand"><th class="sticky-name">סה״כ</th><td class="sticky-unit"></td><td class="sticky-total">${r.participants}</td>${r.matrix.roomTotals.map((n,i)=>`<td class="${over.has(r.matrix.rooms[i])?'over':''}">${n}</td>`).join('')}<td>${r.participants-r.matrix.roomTotals.reduce((a,b)=>a+b,0)}</td></tr></tbody></table></div></section>`}
function render(){
  const r=result;$('adjust').hidden=!r;$('download').hidden=!r;$('report').hidden=!r;$('envelopeSection').hidden=!r;$('matrixCopySection').hidden=!r;$('next').hidden=!r;$('nextHelp').hidden=!r||!!pdfInfo;
  if(!r){$('results').innerHTML='<div class="empty"><span>▦</span><h3>תוצאות השיבוץ יוצגו כאן לאחר החישוב.</h3></div>';return}
  const loads=r.rooms.filter(x=>x.kind==='רגיל').map(x=>x.count);
  const ruleSummary=r.singleDesk?`מצב בודד בשולחן · עד 20 תלמידים בחדר · ${r.singleDeskIdeal?'נשמר יעד של עד 10 מכל סוג יחידות':'נעשה שימוש בהקלה של עד 13 מסוג יחידות'}`:`${r.overflow} חדרים חורגים, מתוך מכסה של ${r.quota}`;
  $('results').innerHTML=`<div class="summary"><div class="stat"><b>${r.participants}</b><span>תלמידים</span></div><div class="stat"><b>${r.total}</b><span>חדרים</span></div><div class="stat"><b>${loads.length?Math.min(...loads)+'–'+Math.max(...loads):'—'}</b><span>תפוסה בחדר רגיל</span></div></div><div class="success">כל בדיקות התקינות עברו.<br>${r.regular} רגילים · ${r.dedicated} ייעודיים · ${r.special} מיוחדים<br>${ruleSummary}</div><p class="note">${r.minimal?'מספר חדרים מינימלי הוכח.':'שיבוץ למספר החדרים שביקשת.'} ${r.balanced?'פער התפוסה המינימלי הוכח.':'נמצא פתרון תקין; מיטביות האיזון לא הוכחה בזמן החיפוש.'} ${r.splitOptimal?'פיצול הקבוצות צומצם באופן מיטבי עבור פער זה.':''}</p>${baseTotal!==r.total?`<div class="info">תוצאת הבסיס: ${baseTotal} חדרים · תוצאה נוכחית: ${r.total} חדרים</div>`:''}${matrix(r)}<details><summary>פירוט חדרים</summary><div class="tablewrap"><table><thead><tr><th>חדר</th><th>סוג</th><th>תלמידים</th><th>רמות לימוד</th><th>חריגה</th></tr></thead><tbody>${r.rooms.map(x=>`<tr><td>${x.room}</td><td>${esc(x.kind)}</td><td>${x.count}</td><td>${Object.entries(x.units).map(([u,n])=>esc(u)+': '+n).join(' · ')}</td><td>${x.overflow?'מעל '+r.settings.normal:'—'}</td></tr>`).join('')}</tbody></table></div></details><details><summary>פירוט קבוצות המורים</summary><div class="tablewrap"><table><thead><tr><th>מורה</th><th>יחידות</th><th>חדר: תלמידים</th></tr></thead><tbody>${r.splits.map(x=>`<tr><td>${esc(x.teacher)}</td><td>${esc(x.unit)}</td><td>${Object.entries(x.rooms).map(([n,c])=>n+': '+c).join(' · ')}</td></tr>`).join('')}</tbody></table></div></details>`;
  $('download').textContent=`הורדת קובץ השיבוץ — ${r.total} חדרים`;refreshRoomOptions();target();
}

function refreshRoomOptions(){
  const options=(result?.rooms||[]).map(x=>`<option value="${x.room}">חדר ${x.room}</option>`).join('');
  document.querySelectorAll('.note-room').forEach(select=>{const old=select.value;select.innerHTML='<option value="">בחירת חדר</option>'+options;if([...select.options].some(x=>x.value===old))select.value=old});
}
function addNoteRow(){
  if(noteRows().length>=2)return;const row=document.createElement('div');row.className='note-row';
  row.innerHTML=`<label><span>מספר חדר</span><select class="note-room"><option value="">בחירת חדר</option></select></label><label class="note-grow"><span>הערה לחדר</span><input class="note-text" maxlength="120" placeholder="לדוגמה: אין להכניס מוצרי חלב לכיתה"><small><span class="char-count">0</span>/120</small></label><button type="button" class="remove-note smallbutton" aria-label="הסרת ההערה">הסר</button>`;
  $('noteRows').appendChild(row);refreshRoomOptions();row.querySelector('.remove-note').onclick=()=>{row.remove();if(!noteRows().length)addNoteRow();invalidatePdf()};
  row.querySelectorAll('input,select').forEach(el=>el.oninput=()=>{row.querySelector('.char-count').textContent=row.querySelector('.note-text').value.length;invalidatePdf()});envelopeControls();
}
function collectNotes(){
  const notes=[];for(const row of noteRows()){const room=row.querySelector('.note-room').value,text=row.querySelector('.note-text').value.trim();if(!room&&!text)continue;if(!room||!text)throw Error('בכל הערה יש לבחור חדר ולהזין טקסט.');notes.push({room:Number(room),text})}return notes;
}

$('run').onclick=()=>run('base');$('rebalance').onclick=()=>run('adjust');$('delta').oninput=target;document.querySelectorAll('[name=op]').forEach(e=>e.onchange=target);
$('cancel').onclick=async()=>{clearTimeout(pollTimer);try{await api('/cancel',{});poll()}catch(e){error(e.message)}};
$('reset').onclick=async()=>{try{await api('/reset',{});poll()}catch(e){error(e.message)}};
function save(blob,name){const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),2000)}
async function downloadWorkbook(){try{save(await api('/download'),filename.replace(/\.(xlsx|xlsm)$/i,`_assigned_${result.total}rooms.$1`))}catch(e){error(e.message);setRoomMapError(e.message)}}
$('download').onclick=downloadWorkbook;
$('downloadUpdatedWorkbook').onclick=downloadWorkbook;
$('report').onclick=()=>{const {assignments,...report}=result;save(new Blob([JSON.stringify(report,null,2)],{type:'application/json;charset=utf-8'}),'room-assignment-report.json')};

$('makeMatrixPdf').onclick=async()=>{
  try{matrixPdfBusy=true;$('makeMatrixPdf').disabled=true;error('');$('matrixPdfSuccess').hidden=true;$('matrixPdfStatus').textContent='מכין עותק PDF של המטריצה…';matrixPdfInfo=await api('/matrix-pdf',{});$('matrixPdfDetails').textContent=`${matrixPdfInfo.teachers} שורות מורים · ${matrixPdfInfo.rooms} חדרים · ${matrixPdfInfo.students} תלמידים · ${matrixPdfInfo.pages} עמודים`;$('matrixPdfSuccess').hidden=false;$('matrixPdfStatus').textContent='הפקת הקובץ הסתיימה בהצלחה.'}
  catch(e){error(e.message);$('matrixPdfStatus').textContent='הפקת מטריצת המורים והחדרים נכשלה.'}
  finally{matrixPdfBusy=false;$('makeMatrixPdf').disabled=false}
};
$('downloadMatrixPdf').onclick=async()=>{try{save(await api('/download-matrix-pdf'),matrixPdfInfo?.filename||'teachers_rooms_matrix.pdf')}catch(e){error(e.message)}};
$('openMatrixPdf').onclick=async()=>{try{await api('/open-matrix-pdf',{})}catch(e){error(e.message)}};
$('openMatrixOutput').onclick=async()=>{try{await api('/open-output',{})}catch(e){error(e.message)}};

function roomMapInputs(){return [...document.querySelectorAll('.physical-room')]}
function setRoomMapError(message){$('roomMapError').hidden=!message;$('roomMapError').textContent=message||''}
function updateRoomMapControls(){
  const inputs=roomMapInputs(),seen=new Map();let valid=inputs.length>0;
  for(const input of inputs){input.setCustomValidity('');const value=input.value.trim();if(!value){valid=false;continue}if(seen.has(value)){input.setCustomValidity('מספר חדר כפול');seen.get(value).setCustomValidity('מספר חדר כפול');valid=false}else seen.set(value,input)}
  $('makeTeacherReports').disabled=teacherReportsBusy||!valid;
}
function buildRoomMap(){
  const previous=Object.fromEntries(roomMapInputs().map(input=>[input.dataset.room,input.value]));
  const rooms=result?.matrix?.rooms||[];$('roomMapSummary').textContent=`הוקצו ${rooms.length} חדרים למבחן. יש להזין ${rooms.length} מספרי חדרים פיזיים.`;
  $('roomMapRows').innerHTML=rooms.map(room=>`<tr><td>חדר ${room}</td><td><input class="physical-room" data-room="${room}" maxlength="40" required autocomplete="off" value="${esc(previous[room]||savedRoomLabels[room]||'')}" placeholder="לדוגמה: י1 121" aria-label="חדר בחינה פיזי עבור חדר ${room}"></td></tr>`).join('');
  roomMapInputs().forEach(input=>input.oninput=()=>{invalidateTeacherReports();setRoomMapError('');updateRoomMapControls()});invalidateTeacherReports();updateRoomMapControls();
}
function showRoomMap(){if(!result||!pdfInfo)return;buildRoomMap();$('mainScreen').hidden=true;$('roomMapScreen').hidden=false;window.scrollTo({top:0,behavior:'smooth'})}
function showMain(){$('roomMapScreen').hidden=true;$('mainScreen').hidden=false;window.scrollTo({top:0,behavior:'smooth'})}
function collectRoomLabels(){
  const labels={};for(const input of roomMapInputs()){const value=input.value.trim();if(!value)throw Error(`חסר מספר חדר בחינה עבור חדר ${input.dataset.room}.`);labels[input.dataset.room]=value}
  if(new Set(Object.values(labels)).size!==Object.values(labels).length)throw Error('כל מספר חדר בחינה חייב להיות ייחודי.');return labels;
}
$('next').onclick=showRoomMap;$('back').onclick=showMain;$('backAfterReports').onclick=showMain;
$('makeTeacherReports').onclick=async()=>{
  try{const roomLabels=collectRoomLabels();teacherReportsBusy=true;updateRoomMapControls();setRoomMapError('');$('teacherReportsSuccess').hidden=true;$('teacherReportsStatus').textContent='מפיק דוחות מורים ורשימת הקראה…';teacherReportsInfo=await api('/teacher-reports',{roomLabels});savedRoomLabels=roomLabels;$('teacherReportsDetails').textContent=`נוצרו ${teacherReportsInfo.teachers} קובצי PDF למורים עבור ${teacherReportsInfo.students} תלמידים, ורשימת הקראה עבור ${teacherReportsInfo.readingStudents} תלמידים. יש להוריד גם את קובץ Excel המעודכן שבו נשמרו הנעילה ומספרי החדרים.`;$('teacherFileList').innerHTML='<b>הקבצים שנוצרו:</b><ul>'+teacherReportsInfo.files.map(name=>`<li>${esc(name)}</li>`).join('')+`<li>${esc(teacherReportsInfo.readingFilename)}</li></ul>`;$('teacherReportsSuccess').hidden=false;$('teacherReportsStatus').textContent='השיבוץ ורשימת ההקראה הופקו. הנעילה ומיפוי החדרים נשמרו בגיליון „ניהול” של קובץ Excel המעודכן.'}
  catch(e){setRoomMapError(e.message);$('teacherReportsStatus').textContent='הפקת דוחות המורים נכשלה.'}
  finally{teacherReportsBusy=false;updateRoomMapControls()}
};
$('downloadTeacherReports').onclick=async()=>{try{save(await api('/download-teacher-reports'),teacherReportsInfo?.filename||'teacher_room_assignments.zip')}catch(e){setRoomMapError(e.message)}};
$('downloadReadingList').onclick=async()=>{try{save(await api('/download-reading-list'),teacherReportsInfo?.readingFilename||'reading_list.pdf')}catch(e){setRoomMapError(e.message)}};
$('openTeacherReports').onclick=async()=>{try{await api('/open-teacher-reports',{})}catch(e){setRoomMapError(e.message)}};

$('addNote').onclick=addNoteRow;document.querySelectorAll('input[name=grade]').forEach(x=>x.onchange=()=>{updateGradeDisplay();invalidatePdf();controls()});
$('makePdf').onclick=async()=>{
  try{const grade=selectedGrade();if(!grade)throw Error('יש לבחור שכבת מבחן.');const notes=collectNotes();pdfBusy=true;envelopeControls();error('');$('pdfSuccess').hidden=true;$('pdfStatus').textContent='מכין דפי מעטפות…';pdfInfo=await api('/envelopes',{grade,notes});appLocked=true;$('unlockWrap').hidden=false;$('unlock').checked=false;$('lockNotice').hidden=false;document.body.classList.add('app-locked');$('pdfDetails').textContent=`${pdfInfo.rooms} חדרים · ${pdfInfo.students} נבחנים · ${pdfInfo.pages} עמודים · נשמר גם בתיקיית Output`;$('pdfSuccess').hidden=false;$('pdfStatus').textContent='הפקת הקובץ הסתיימה בהצלחה. המערכת נעולה לשיבוצים.'}
  catch(e){error(e.message);$('pdfStatus').textContent='הפקת דפי המעטפות נכשלה.'}
  finally{pdfBusy=false;controls()}
};
$('downloadPdf').onclick=async()=>{try{save(await api('/download-pdf'),pdfInfo?.filename||'exam_envelopes.pdf')}catch(e){error(e.message)}};
$('openPdf').onclick=async()=>{try{await api('/open-pdf',{})}catch(e){error(e.message)}};
$('openOutput').onclick=async()=>{try{await api('/open-output',{})}catch(e){error(e.message)}};
$('unlock').onchange=async()=>{if(!$('unlock').checked)return;try{const reply=await api('/unlock',{unlocked:true});appLocked=!!reply.locked;$('unlockWrap').hidden=true;$('lockNotice').hidden=true;document.body.classList.remove('app-locked');invalidatePdf();$('status').textContent='הנעילה שוחררה. ניתן לערוך ולחשב שיבוץ מחדש.';controls()}catch(e){$('unlock').checked=false;error(e.message)}};
$('exit').onclick=async()=>{if(!confirm('לסגור את האפליקציה המקומית? הורידו קודם את התוצאה הרצויה.'))return;try{await api('/shutdown',{})}finally{window.close()}};

setInterval(()=>api('/heartbeat').catch(()=>{}),15000);api('/heartbeat').catch(()=>{});

updateGradeDisplay();updateSingleDeskInfo();addNoteRow();controls();
