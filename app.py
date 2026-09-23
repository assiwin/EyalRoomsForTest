import json, os, sys, io, secrets, threading, traceback, webbrowser, multiprocessing as mp, time
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
from engine import read_book, solve, write_book, restore_result
from envelopes import create_envelopes_pdf
from matrix_pdf import create_matrix_pdf
from schedule_pdf import create_schedule_pdf
from teacher_reports import create_teacher_reports
from reading_list import create_reading_list_pdf
from workbook_management import read_management, update_management

DEBUG = os.environ.get('EXAM_ROOM_DEBUG') == '1'

def work(conn,book,config,target):
    try:conn.send({'ok':True,'result':solve(book,config,target)})
    except Exception as e:conn.send({'ok':False,'error':str(e) or 'בדיקת תקינות נכשלה. לא נוצר קובץ.'})
    finally:conn.close()

def main():
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    app_dir=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    output_dir=app_dir/'Output'
    token=secrets.token_urlsafe(32);lock=threading.RLock();state={'process':None,'book':None,'result':None,'output':None,'baseTotal':None,'envelope':None,'envelopePath':None,'envelopeMeta':None,'matrixPdf':None,'matrixPdfPath':None,'matrixPdfMeta':None,'schedulePdfPath':None,'teacherReportsZip':None,'teacherReportsZipPath':None,'teacherReportsDir':None,'teacherReportsMeta':None,'readingList':None,'readingListPath':None,'management':{'roomLabels':{},'locked':False},'lastHeartbeat':time.monotonic(),'heartbeatStarted':False}
    def cancel():
        p=state.get('process')
        if p is not None:
            if p.is_alive():p.terminate()
            p.join(timeout=2);state['process']=None
            state['conn'].close()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,format,*args):
            if DEBUG:super().log_message(format,*args)
        def send(self,status,body,ctype='application/json; charset=utf-8'):
            if isinstance(body,dict):body=json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
        def auth(self):
            if self.headers.get('X-App-Token')!=token:self.send(403,{'error':'גישה לא מורשית.'});return False
            return True
        def valid_host(self):
            if self.headers.get('Host')!=f'127.0.0.1:{server.server_port}':
                self.send(403,{'error':'Host not allowed'});return False
            return True
        def do_GET(self):
            if not self.valid_host():return
            path=urlparse(self.path).path
            if path=='/':
                # Local bootstrap page; mutating requests require per-run token and same-origin access.
                self.send(200,(base/'web/index.html').read_text(encoding='utf8').replace('__TOKEN__',token).encode(),'text/html; charset=utf-8');return
            if path in ['/style.css','/ui.js']:
                self.send(200,(base/'web'/path[1:]).read_bytes(),'text/css; charset=utf-8' if path.endswith('css') else 'text/javascript; charset=utf-8');return
            if not self.auth():return
            with lock:
                if path=='/status':
                    p=state.get('process')
                    if p is not None:
                        if state['conn'].poll():
                            msg=state['conn'].recv();p.join(timeout=1);state['process']=None;state['conn'].close()
                            if msg['ok']:
                                try:
                                    result=msg['result'];output=write_book(state['data'],state['book'],result);state['result']=result;state['output']=output;state['envelope']=None;state['envelopePath']=None;state['envelopeMeta']=None;state['matrixPdf']=None;state['matrixPdfPath']=None;state['matrixPdfMeta']=None;state['teacherReportsZip']=None;state['teacherReportsZipPath']=None;state['teacherReportsDir']=None;state['teacherReportsMeta']=None
                                    if state['isBase']:state['baseTotal']=result['total'];state['baseResult']=result;state['baseOutput']=output
                                except Exception as e:msg={'ok':False,'error':'שמירת הפלט נכשלה: '+str(e)}
                            if not msg['ok']:state['error']=msg['error']
                        elif not p.is_alive():p.join();state['process']=None;state['error']='החישוב הופסק ללא תוצאה. ניתן לנסות שוב.'
                    self.send(200,{'busy':state['process'] is not None,'result':state['result'],'baseTotal':state['baseTotal'],'error':state.get('error')});return
                if path=='/heartbeat':
                    state['lastHeartbeat']=time.monotonic();state['heartbeatStarted']=True;self.send(200,{'ok':True});return
                if path=='/download' and state.get('output'):
                    self.send(200,state['output'],'application/octet-stream');return
                if path=='/download-pdf' and state.get('envelope'):
                    self.send(200,state['envelope'],'application/pdf');return
                if path=='/download-matrix-pdf' and state.get('matrixPdf'):
                    self.send(200,state['matrixPdf'],'application/pdf');return
                if path=='/download-teacher-reports' and state.get('teacherReportsZip'):
                    self.send(200,state['teacherReportsZip'],'application/zip');return
                if path=='/download-reading-list' and state.get('readingList'):
                    self.send(200,state['readingList'],'application/pdf');return
            self.send(404,{'error':'לא נמצאה תוצאה.'})
        def do_POST(self):
            if not self.valid_host():return
            if not self.auth():return
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<=length<=20_000_000:raise ValueError('הקובץ גדול מדי. עד 20 MB.')
                raw=self.rfile.read(length);path=urlparse(self.path).path
                with lock:
                    if path=='/upload':
                        cancel();state.update(book=None,result=None,output=None,baseTotal=None,error=None,envelope=None,envelopePath=None,envelopeMeta=None,matrixPdf=None,matrixPdfPath=None,matrixPdfMeta=None,teacherReportsZip=None,teacherReportsZipPath=None,teacherReportsDir=None,teacherReportsMeta=None,readingList=None,readingListPath=None)
                        name=unquote(self.headers.get('X-Filename','input.xlsx'))
                        if Path(name).suffix.lower() not in ['.xlsm','.xlsx']:raise ValueError('נדרש קובץ XLSX או XLSM.')
                        book=read_book(raw);management=read_management(raw);restored_result=restore_result(book) if management.get('locked') else None;base_total=restored_result.get('total') if restored_result else None
                        state.update(data=raw,book=book,name=Path(name).name,management=management,result=restored_result,output=raw if restored_result else None,baseTotal=base_total,baseResult=restored_result,baseOutput=raw if restored_result else None)
                        self.send(200,{'records':len(book['records']),'participants':len(book['participants']),'special':book['special'],'dedicated':book['dedicated'],'management':management,'restoredResult':restored_result,'baseTotal':base_total,'grade':''});return
                    if path=='/run':
                        if not state['book']:raise ValueError('יש לטעון קובץ תחילה.')
                        if state['management'].get('locked'):raise ValueError('המערכת נעולה לשיבוצים. סמנו „שחרר נעילה” ליד טעינת הקובץ כדי לערוך.')
                        if state['process'] is not None:raise ValueError('חישוב כבר פועל.')
                        payload=json.loads(raw);c=payload['settings'];mode=payload.get('mode','base');target=None
                        if mode!='base':
                            if not state['baseTotal']:raise ValueError('נדרש שיבוץ בסיס.')
                            if c!=state['baseResult']['settings']:raise ValueError('ההגדרות השתנו. יש לחשב שיבוץ בסיס חדש.')
                            delta=payload.get('delta');op=payload.get('op')
                            if type(delta) is not int or delta<1 or op not in ['add','remove']:raise ValueError('מספר החדרים לשינוי אינו תקין.')
                            target=state['baseTotal']+(delta if op=='add' else -delta)
                        else:state.update(result=None,output=None,baseTotal=None,envelope=None,envelopePath=None,envelopeMeta=None,matrixPdf=None,matrixPdfPath=None,matrixPdfMeta=None,teacherReportsZip=None,teacherReportsZipPath=None,teacherReportsDir=None,teacherReportsMeta=None)
                        recv,send=mp.Pipe(duplex=False);p=mp.Process(target=work,args=(send,state['book'],c,target));p.start();send.close();state.update(process=p,conn=recv,isBase=mode=='base',error=None)
                        self.send(200,{'started':True});return
                    if path=='/cancel':cancel();state['error']=None;self.send(200,{'ok':True});return
                    if path=='/invalidate':cancel();state.update(result=None,output=None,baseTotal=None,error=None,envelope=None,envelopePath=None,envelopeMeta=None,matrixPdf=None,matrixPdfPath=None,matrixPdfMeta=None,teacherReportsZip=None,teacherReportsZipPath=None,teacherReportsDir=None,teacherReportsMeta=None);self.send(200,{'ok':True});return
                    if path=='/reset':
                        cancel()
                        if not state['baseTotal']:raise ValueError('אין שיבוץ בסיס.')
                        state.update(result=state['baseResult'],output=state['baseOutput'],error=None,envelope=None,envelopePath=None,envelopeMeta=None,matrixPdf=None,matrixPdfPath=None,matrixPdfMeta=None,teacherReportsZip=None,teacherReportsZipPath=None,teacherReportsDir=None,teacherReportsMeta=None);self.send(200,{'ok':True});return
                    if path=='/matrix-pdf':
                        if state.get('process') is not None:raise ValueError('יש להמתין לסיום החישוב.')
                        if not state.get('result'):raise ValueError('נדרש שיבוץ תקין לפני הפקת המטריצה.')
                        pdf,meta=create_matrix_pdf(state['result'],base)
                        output_dir.mkdir(parents=True,exist_ok=True)
                        stamp=datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                        target=output_dir/f'teachers_rooms_matrix_{stamp}.pdf';target.write_bytes(pdf)
                        state.update(matrixPdf=pdf,matrixPdfPath=target,matrixPdfMeta=meta)
                        self.send(200,{**meta,'filename':target.name,'path':str(target)});return
                    if path=='/schedule-pdf':
                        payload=json.loads(raw or b'{}');pdf,meta=create_schedule_pdf(payload.get('schedule'),base)
                        output_dir.mkdir(parents=True,exist_ok=True)
                        stamp=datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                        target=output_dir/f'exam_times_{stamp}.pdf';target.write_bytes(pdf)
                        state['schedulePdfPath']=target
                        if os.name=='nt':os.startfile(str(output_dir))
                        else:webbrowser.open(output_dir.resolve().as_uri())
                        self.send(200,{**meta,'filename':target.name,'path':str(target)});return
                    if path=='/teacher-reports':
                        if state.get('process') is not None:raise ValueError('יש להמתין לסיום החישוב.')
                        if not state.get('book') or not state.get('result'):raise ValueError('נדרש שיבוץ תקין לפני הפקת דוחות המורים.')
                        payload=json.loads(raw or b'{}');labels=payload.get('roomLabels')
                        if not isinstance(labels,dict):raise ValueError('יש להזין את מספרי חדרי הבחינה.')
                        try:room_labels={int(key):value for key,value in labels.items()}
                        except (TypeError,ValueError):raise ValueError('מיפוי מספרי חדרי הבחינה אינו תקין.')
                        archive,reports,meta=create_teacher_reports(state['book'],state['result'],room_labels,base)
                        reading_pdf,reading_meta=create_reading_list_pdf(state['book'],state['result'],room_labels,base)
                        output_dir.mkdir(parents=True,exist_ok=True)
                        stamp=datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                        report_dir=output_dir/f'teacher_reports_{stamp}';report_dir.mkdir()
                        for report_name,report_data in reports.items():(report_dir/report_name).write_bytes(report_data)
                        reading_target=report_dir/'reading_list.pdf';reading_target.write_bytes(reading_pdf)
                        zip_target=output_dir/f'teacher_reports_{stamp}.zip';zip_target.write_bytes(archive)
                        source=state.get('output') or state['data'];updated=update_management(source,room_labels=room_labels,locked=state['management'].get('locked',False))
                        state['management']['roomLabels']=room_labels;state.update(output=updated,teacherReportsZip=archive,teacherReportsZipPath=zip_target,teacherReportsDir=report_dir,teacherReportsMeta=meta,readingList=reading_pdf,readingListPath=reading_target)
                        self.send(200,{**meta,**reading_meta,'filename':zip_target.name,'readingFilename':reading_target.name,'path':str(report_dir)});return
                    if path=='/envelopes':
                        if state.get('process') is not None:raise ValueError('יש להמתין לסיום החישוב.')
                        if not state.get('book') or not state.get('result'):raise ValueError('נדרש שיבוץ תקין לפני הפקת מעטפות.')
                        payload=json.loads(raw);grade=payload.get('grade');notes=payload.get('notes',[])
                        pdf,meta=create_envelopes_pdf(state['book'],state['result'],grade,notes,base)
                        output_dir.mkdir(parents=True,exist_ok=True)
                        stamp=datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                        target=output_dir/f'exam_envelopes_{stamp}.pdf';target.write_bytes(pdf)
                        source=state.get('output') or state['data'];state['output']=update_management(source,room_labels=state['management'].get('roomLabels',{}),locked=True);state['management']['locked']=True
                        state.update(envelope=pdf,envelopePath=target,envelopeMeta=meta)
                        self.send(200,{**meta,'filename':target.name,'path':str(target)});return
                    if path=='/unlock':
                        if not state.get('book'):raise ValueError('יש לטעון קובץ תחילה.')
                        payload=json.loads(raw or b'{}');unlocked=bool(payload.get('unlocked'))
                        source=state.get('output') or state['data'];state['output']=update_management(source,room_labels=state['management'].get('roomLabels',{}),locked=not unlocked);state['management']['locked']=not unlocked
                        if unlocked:state.update(envelope=None,envelopePath=None,envelopeMeta=None)
                        self.send(200,{'locked':state['management']['locked']});return
                    if path in ['/open-pdf','/open-matrix-pdf','/open-teacher-reports','/open-output']:
                        target=state.get('envelopePath') if path=='/open-pdf' else state.get('matrixPdfPath') if path=='/open-matrix-pdf' else state.get('teacherReportsDir') if path=='/open-teacher-reports' else output_dir
                        if path in ['/open-pdf','/open-matrix-pdf','/open-teacher-reports'] and (not target or not Path(target).exists()):raise ValueError('לא נמצא קובץ או תיקיית פלט לפתיחה.')
                        if path=='/open-output':output_dir.mkdir(parents=True,exist_ok=True)
                        if os.name=='nt':os.startfile(str(target))
                        else:webbrowser.open(Path(target).resolve().as_uri())
                        self.send(200,{'ok':True});return
                    if path=='/shutdown':cancel();self.send(200,{'ok':True});threading.Thread(target=server.shutdown,daemon=True).start();return
                self.send(404,{'error':'פעולה לא מוכרת.'})
            except (ValueError,KeyError,AssertionError) as e:self.send(400,{'error':str(e) or 'נתוני בקשה לא תקינים.'})
            except Exception as e:
                if DEBUG:
                    traceback.print_exc()
                    self.send(500,{'error':f'{type(e).__name__}: {e}'})
                else:self.send(500,{'error':'הפעולה נכשלה. נסו לטעון מחדש את הקובץ.'})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    def heartbeat_watch():
        while True:
            time.sleep(10)
            if state.get('heartbeatStarted') and time.monotonic()-state.get('lastHeartbeat',0)>120:
                threading.Thread(target=server.shutdown,daemon=True).start();return
    threading.Thread(target=heartbeat_watch,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}/';print('Exam Room App: '+url,flush=True)
    if '--no-browser' not in sys.argv:threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    finally:cancel();server.server_close()

if __name__=='__main__':mp.freeze_support();main()
