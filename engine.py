"""Local exam-room optimizer. Assignment output changes only participant I cells."""
import io, zipfile, re, posixpath, math, time, collections, html
import xml.etree.ElementTree as ET
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def tag(name): return '{'+NS['s']+'}'+name
def norm(v): return str(v or '').strip()
def one(v): return norm(v) in ('1','1.0')
def clas(v): return re.sub(r'[\s\-״"׳\']','',norm(v))
def read_book(data):
    try:
        z=zipfile.ZipFile(io.BytesIO(data))
        if sum(x.file_size for x in z.infolist())>100_000_000: raise ValueError('הקובץ גדול מדי לאחר פתיחה.')
        if len(set(z.namelist()))!=len(z.namelist()): raise ValueError('מבנה ZIP כפול אינו נתמך.')
        if any(n.startswith('_xmlsignatures/') for n in z.namelist()): raise ValueError('אין לשנות חוברת חתומה דיגיטלית.')
        wb=ET.fromstring(z.read('xl/workbook.xml')); rel=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets={r.attrib['Id']:r.attrib['Target'] for r in rel}
        sheet=next((s for s in wb.findall('s:sheets/s:sheet',NS) if s.attrib['name']=='dbase'),None)
        if sheet is None: raise ValueError('לא נמצא גיליון dbase.')
        target=targets[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
        text=z.read(path).decode('utf-8'); root=ET.fromstring(text)
        if root.find('s:sheetProtection',NS) is not None: raise ValueError('הגיליון מוגן. יש להסיר הגנה ב־Excel לפני השיבוץ.')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(t.text or '' for t in si.iter(tag('t'))) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        records=[]; header={}
        for row in root.findall('s:sheetData/s:row',NS):
            rn=int(row.attrib['r']); cells={}
            for c in row.findall('s:c',NS):
                col=re.sub(r'\d','',c.attrib['r']); val=c.find('s:v',NS); v=val.text if val is not None else ''
                if c.attrib.get('t')=='s':v=strings[int(v)]
                elif c.attrib.get('t')=='inlineStr':v=''.join(t.text or '' for t in c.iter(tag('t')))
                if c.find('s:f',NS) is not None and col in ['A','B','C','G','H','J','K','L','M']:
                    raise ValueError(f'שורה {rn}: נתון קלט מחושב בעמודה {col}. יש להמיר נתוני קלט לערכים בעותק עבודה.')
                cells[col]=norm(v)
            if rn==1:header=cells;continue
            if not cells.get('A') and not cells.get('B'):continue
            records.append({
                'row':rn,'id':cells.get('A',''),'name':cells.get('B',''),
                'class':clas(cells.get('C')),'extra_time':cells.get('D',''),
                'enlargement':cells.get('E',''),'reading':cells.get('F',''),
                'teacher':cells.get('G',''),'unit':cells.get('H',''),
                'assigned':cells.get('I',''),
                'active':one(cells.get('J')),
                'flags':[k for k in 'KLM' if one(cells.get(k))],
                'problematic':one(cells.get('N'))
            })
        if not all(header.get(k) for k in ['A','B','C','G','H','I','J','K','L','M']):raise ValueError('מבנה הכותרות A–M אינו תואם למבנה הנדרש.')
        p=[r for r in records if r['active']]; seen=set(); errors=[]
        for r in p:
            if not r['id'] or not r['name'] or not r['teacher'] or not r['class'] or r['unit'] not in ['3','3א','4','5']:errors.append(f"שורה {r['row']}: חסר נתון חובה או רמת לימוד לא תקינה.")
            if r['id'] in seen:errors.append(f"שורה {r['row']}: מזהה תלמיד כפול.")
            seen.add(r['id'])
            if len(r['flags'])>1 or (r['flags'] and r['class'] in ['י7','יא7','יב7']):errors.append(f"שורה {r['row']}: שיוך סותר לחדרים ייעודיים או מיוחדים.")
        if errors:raise ValueError('\n'.join(errors[:25]))
        if not p:raise ValueError('אין משתתפים המסומנים 1 בעמודה J.')
        return {'records':records,'participants':p,'path':path,'text':text,'special':dict(collections.Counter(r['flags'][0] for r in p if r['flags'])),'dedicated':sorted(set(r['class'] for r in p if r['class'] in ['י7','יא7','יב7']))}
    except (zipfile.BadZipFile,KeyError,ET.ParseError,IndexError,UnicodeError) as e:
        raise ValueError('לא ניתן לקרוא את הקובץ. נדרש XLSX או XLSM תקין, ללא סיסמה.') from e

def settings(c):
    for k,lo,hi in [('normal',1,100),('maximum',1,100),('percent',0,100),('level',1,100),('limit',1,25)]:
        if type(c.get(k)) is not int or not lo<=c[k]<=hi:raise ValueError('הגדרה מספרית לא תקינה: '+k)
    if type(c.get('singleDesk',False)) is not bool:raise ValueError('הגדרת בודד בשולחן אינה תקינה.')
    if c['normal']>c['maximum']:raise ValueError('התקרה הרגילה גדולה מהתקרה המרבית.')
    return c

def solve(book,c,target=None):
    if c.get('singleDesk',False):return solve_single_desk(book,c,target)
    settings(c); p=book['participants']; groups=collections.defaultdict(list); special=collections.defaultdict(list); dedicated=collections.defaultdict(list)
    for r in p:
        if r['flags']:special[r['flags'][0]].append(r)
        elif r['class'] in ['י7','יא7','יב7']:dedicated[r['class']].append(r)
        else:groups[(r['teacher'],r['unit'])].append(r)
    for k,rr in special.items():
        cap=c.get('special',{}).get(k)
        if type(cap) is not int or cap<len(rr):raise ValueError(f'בחדר {k} יש {len(rr)} תלמידים. נדרשת קיבולת מאושרת מתאימה; לא מתבצע פיצול אוטומטי.')
    for k,rr in dedicated.items():
        u=collections.Counter(r['unit'] for r in rr)
        if len(rr)>c['maximum'] or max(u.values())>c['level'] or ('3' in u and '3א' in u):raise ValueError('הכיתה '+k+' אינה נכנסת לחדר ייעודי יחיד תחת הכללים. יש לתקן את הכללים או את הקלט.')
    extra=len(special)+len(dedicated); keys=list(groups); sizes=[len(groups[k]) for k in keys]; G=len(keys); N=sum(sizes); units=collections.Counter()
    for k,n in zip(keys,sizes):units[k[1]]+=n
    for k,n in zip(keys,sizes):
        if n>c['level']*(2 if n<=32 else 3):raise ValueError('לא ניתן לעמוד במגבלת פיצול הקבוצה: '+k[0]+' / '+k[1])
    lower=max([math.ceil(N/c['maximum']),math.ceil(units['3']/c['level'])+math.ceil(units['3א']/c['level'])]+[math.ceil(n/c['level']) for n in units.values()]) if N else 0
    if target is not None and (type(target) is not int or not extra<=target<=c['limit']):raise ValueError('מספר החדרים המבוקש מחוץ לטווח.')
    candidates=[target-extra] if target is not None else range(lower,c['limit']-extra+1)
    deadline=time.monotonic()+110; solution=None; balanced=False; split_optimal=False
    for R in candidates:
        if R<lower or R>N or (N and R<1):continue
        if N>R*c['normal']+math.floor(R*c['percent']/100)*(c['maximum']-c['normal']):continue
        if N==0:solution=(0,np.array([]));balanced=True;split_optimal=True;break
        # integer allocations x, use flags y, overflow o, type z; group3 and teacher3 flags; min/max load
        T=list(dict.fromkeys(k[0] for k in keys)); nvar=2*G*R+2*R+G+len(T)+2
        X=lambda g,r:g*R+r;Y=lambda g,r:G*R+g*R+r;O=lambda r:2*G*R+r;Z=lambda r:2*G*R+R+r
        Q=lambda g:2*G*R+2*R+g;W=lambda t:2*G*R+2*R+G+t; LOW=nvar-2;HIGH=nvar-1
        cons=[]
        def add(d,lo,hi):cons.append((d,lo,hi))
        for g,(key,n) in enumerate(zip(keys,sizes)):
            add({X(g,r):1 for r in range(R)},n,n)
            add({**{Y(g,r):1 for r in range(R)},Q(g):-1},0,2)
            if n<=32:add({Q(g):1},0,0)
            add({Q(g):1,W(T.index(key[0])):-1},-np.inf,0)
            for r in range(R):
                add({X(g,r):1,Y(g,r):-min(n,c['level'])},-np.inf,0);add({X(g,r):1,Y(g,r):-1},0,np.inf)
        add({W(t):1 for t in range(len(T))},0,3)
        for r in range(R):
            d={X(g,r):1 for g in range(G)}
            add(d,1,c['maximum']);add({**d,O(r):-(c['maximum']-c['normal'])},-np.inf,c['normal'])
            add({**d,HIGH:-1},-np.inf,0);add({**d,LOW:-1},0,np.inf)
            for u in ['3','3א','4','5']:
                d={X(g,r):1 for g,k in enumerate(keys) if k[1]==u};add(d,0,c['level'])
                if u=='3':add({**d,Z(r):-c['level']},-np.inf,0)
                if u=='3א':add({**d,Z(r):c['level']},-np.inf,c['level'])
            if r<R-1:add({**{X(g,r):1 for g in range(G)},**{X(g,r+1):-1 for g in range(G)}},0,np.inf)
        add({O(r):1 for r in range(R)},0,math.floor(R*c['percent']/100))
        ub=np.ones(nvar);ub[:G*R]=c['level'];ub[-2:]=c['maximum']
        def run(cost,seconds):
            A=lil_matrix((len(cons),nvar));a=[];b=[]
            for j,(d,l,h) in enumerate(cons):
                for k,v in d.items():A[j,k]=v
                a.append(l);b.append(h)
            return milp(cost,integrality=np.ones(nvar),bounds=Bounds(np.zeros(nvar),ub),constraints=LinearConstraint(A.tocsr(),a,b),options={'time_limit':max(1,min(seconds,deadline-time.monotonic())),'mip_rel_gap':0})
        cost=np.zeros(nvar);cost[HIGH]=1;cost[LOW]=-1
        res=run(cost,30)
        if res.x is None:
            if res.status==2:continue
            raise ValueError('החיפוש הסתיים ללא הכרעה. לא הוכח שאין פתרון. נסו להוסיף חדר או להריץ שוב.')
        v=np.rint(res.x).astype(int);balanced=res.status==0
        add({HIGH:1,LOW:-1},-np.inf,int(v[HIGH]-v[LOW]))
        cost=np.zeros(nvar);cost[G*R:2*G*R]=1
        res2=run(cost,15)
        if res2.x is not None:v=np.rint(res2.x).astype(int);split_optimal=res2.status==0
        solution=(R,v);break
    if solution is None:raise ValueError('אין פתרון למספר החדרים המבוקש תחת הכללים הנוכחיים.' if target is not None else 'אין פתרון במסגרת מספר החדרים המרבי. יש לבדוק את ההגדרות.')
    R,v=solution;assign={};kinds={}
    for g,key in enumerate(keys):
        pos=0
        for r in range(R):
            count=int(v[g*R+r])
            for student in groups[key][pos:pos+count]:assign[student['row']]=r+1
            pos+=count;kinds[r+1]='רגיל'
        assert pos==len(groups[key])
    nr=R
    for cl,rr in sorted(dedicated.items()):
        nr+=1;kinds[nr]='כיתה '+cl
        for student in rr:assign[student['row']]=nr
    for k in 'KLM':
        if k in special:
            nr+=1;kinds[nr]={'K':'מצומצם 1','L':'מצומצם 2','M':'נפרד'}[k]
            for student in special[k]:assign[student['row']]=nr
    validate(book,c,assign,R,kinds)
    rooms=[]
    for r in range(1,nr+1):
        members=[s for s in p if assign[s['row']]==r];u=collections.Counter(s['unit'] for s in members)
        rooms.append({'room':r,'kind':kinds[r],'count':len(members),'units':dict(u),'overflow':r<=R and len(members)>c['normal']})
    allgroups=collections.defaultdict(list)
    for student in p:allgroups[(student['teacher'],student['unit'])].append(student)
    order={'3':0,'3א':1,'4':2,'5':3}
    matrixrows=[]
    for key,rr in sorted(allgroups.items(),key=lambda x:(x[0][0],order.get(x[0][1],9),x[0][1])):
        counts=collections.Counter(assign[s['row']] for s in rr)
        matrixrows.append({'teacher':key[0],'unit':key[1],'total':len(rr),'counts':[counts.get(room,0) for room in range(1,nr+1)]})
    roomtotals=[sum(1 for s in p if assign[s['row']]==room) for room in range(1,nr+1)]
    matrix={'rooms':list(range(1,nr+1)),'rows':matrixrows,'roomTotals':roomtotals,'unitTotals':dict(collections.Counter(s['unit'] for s in p))}
    splits=[{'teacher':k[0],'unit':k[1],'rooms':dict(sorted(collections.Counter(assign[s['row']] for s in rr).items()))} for k,rr in groups.items()]
    return {'assignments':assign,'rooms':rooms,'matrix':matrix,'splits':splits,'participants':len(p),'total':nr,'regular':R,'special':len(special),'dedicated':len(dedicated),'overflow':sum(r['overflow'] for r in rooms),'quota':math.floor(R*c['percent']/100),'minimal':target is None,'balanced':balanced,'splitOptimal':split_optimal,'settings':c}

def solve_single_desk(book,c,target=None):
    """Optimize the mock-exam single-desk arrangement without changing special-room rules."""
    settings(c);p=book['participants'];groups=collections.defaultdict(list);special=collections.defaultdict(list);dedicated=collections.defaultdict(list)
    for student in p:
        if student['flags']:special[student['flags'][0]].append(student)
        elif student['class'] in ['י7','יא7','יב7']:dedicated[student['class']].append(student)
        else:groups[(student['teacher'],student['unit'])].append(student)
    for key,members in special.items():
        cap=c.get('special',{}).get(key)
        if type(cap) is not int or cap<len(members):raise ValueError(f'בחדר {key} יש {len(members)} תלמידים. נדרשת קיבולת מאושרת מתאימה; לא מתבצע פיצול אוטומטי.')
    for key,members in dedicated.items():
        units=collections.Counter(student['unit'] for student in members)
        if len(members)>c['maximum'] or max(units.values())>c['level'] or ('3' in units and '3א' in units):raise ValueError('הכיתה '+key+' אינה נכנסת לחדר ייעודי יחיד תחת הכללים. יש לתקן את הכללים או את הקלט.')

    keys=list(groups);sizes=[len(groups[key]) for key in keys];G=len(keys);N=sum(sizes);extra=len(special)+len(dedicated)
    category=lambda unit:'3' if unit in ('3','3א') else unit
    totals=collections.Counter()
    for key,size in zip(keys,sizes):totals[category(key[1])]+=size
    lower=max([math.ceil(N/20)]+[math.ceil(value/13) for value in totals.values()]) if N else 0
    if target is not None and (type(target) is not int or not extra<=target<=c['limit']):raise ValueError('מספר החדרים המבוקש מחוץ לטווח.')
    candidates=[target-extra] if target is not None else range(lower,c['limit']-extra+1)
    deadline=time.monotonic()+110;solution=None;balanced=False;split_optimal=False;ideal=True
    for R in candidates:
        if R<lower or R>N or (N and R<1):continue
        if N==0:solution=(0,np.array([],dtype=int));balanced=True;split_optimal=True;break
        categories=['3','4','5'];C=len(categories);nvar=2*G*R+C*R+2
        X=lambda g,r:g*R+r
        Y=lambda g,r:G*R+g*R+r
        E=lambda u,r:2*G*R+u*R+r
        LOW=nvar-2;HIGH=nvar-1;cons=[]
        def add(values,lo,hi):cons.append((values,lo,hi))
        for g,(key,size) in enumerate(zip(keys,sizes)):
            add({X(g,r):1 for r in range(R)},size,size)
            for r in range(R):
                add({X(g,r):1,Y(g,r):-min(size,13)},-np.inf,0)
                add({X(g,r):1,Y(g,r):-1},0,np.inf)
        for r in range(R):
            load={X(g,r):1 for g in range(G)}
            add(load,1,20);add({**load,HIGH:-1},-np.inf,0);add({**load,LOW:-1},0,np.inf)
            for index,unit in enumerate(categories):
                amount={X(g,r):1 for g,key in enumerate(keys) if category(key[1])==unit}
                add(amount,0,13)
                add({**amount,E(index,r):-1},-np.inf,10)
            if r<R-1:
                add({**{X(g,r):1 for g in range(G)},**{X(g,r+1):-1 for g in range(G)}},0,np.inf)
        upper=np.ones(nvar);upper[:G*R]=13;upper[2*G*R:2*G*R+C*R]=3;upper[-2:]=20
        def run(cost,seconds):
            matrix=lil_matrix((len(cons),nvar));lo=[];hi=[]
            for row,(values,minimum,maximum) in enumerate(cons):
                for col,value in values.items():matrix[row,col]=value
                lo.append(minimum);hi.append(maximum)
            return milp(cost,integrality=np.ones(nvar),bounds=Bounds(np.zeros(nvar),upper),constraints=LinearConstraint(matrix.tocsr(),lo,hi),options={'time_limit':max(1,min(seconds,deadline-time.monotonic())),'mip_rel_gap':0})
        split_cost=np.zeros(nvar);split_cost[G*R:2*G*R]=1
        first=run(split_cost,35)
        if first.x is None:
            if first.status==2:continue
            raise ValueError('החיפוש הסתיים ללא הכרעה. לא הוכח שאין פתרון. נסו להוסיף חדר או להריץ שוב.')
        values=np.rint(first.x).astype(int);split_optimal=first.status==0
        used=int(sum(values[G*R:2*G*R]));add({index:1 for index in range(G*R,2*G*R)},used,used)
        ideal_cost=np.zeros(nvar);ideal_cost[2*G*R:2*G*R+C*R]=1
        second=run(ideal_cost,25)
        if second.x is not None:values=np.rint(second.x).astype(int)
        excess=int(sum(values[2*G*R:2*G*R+C*R]));ideal=excess==0
        add({index:1 for index in range(2*G*R,2*G*R+C*R)},excess,excess)
        balance_cost=np.zeros(nvar);balance_cost[HIGH]=1;balance_cost[LOW]=-1
        third=run(balance_cost,20)
        if third.x is not None:values=np.rint(third.x).astype(int);balanced=third.status==0
        ideal=all(sum(values[X(g,r)] for g,key in enumerate(keys) if category(key[1])==unit)<=10 for unit in categories for r in range(R))
        solution=(R,values);break
    if solution is None:raise ValueError('אין פתרון למספר החדרים המבוקש תחת כללי בודד בשולחן.' if target is not None else 'אין פתרון במסגרת מספר החדרים המרבי עבור מצב בודד בשולחן.')

    R,values=solution;assign={};kinds={}
    for g,key in enumerate(keys):
        position=0
        for room in range(R):
            count=int(values[g*R+room])
            for student in groups[key][position:position+count]:assign[student['row']]=room+1
            position+=count;kinds[room+1]='רגיל'
        assert position==len(groups[key])
    number=R
    for class_name,members in sorted(dedicated.items()):
        number+=1;kinds[number]='כיתה '+class_name
        for student in members:assign[student['row']]=number
    for key in 'KLM':
        if key in special:
            number+=1;kinds[number]={'K':'מצומצם 1','L':'מצומצם 2','M':'נפרד'}[key]
            for student in special[key]:assign[student['row']]=number
    validate(book,c,assign,R,kinds)
    rooms=[]
    for room in range(1,number+1):
        members=[student for student in p if assign[student['row']]==room];units=collections.Counter(student['unit'] for student in members)
        rooms.append({'room':room,'kind':kinds[room],'count':len(members),'units':dict(units),'overflow':False})
    all_groups=collections.defaultdict(list)
    for student in p:all_groups[(student['teacher'],student['unit'])].append(student)
    order={'3':0,'3א':1,'4':2,'5':3};matrix_rows=[]
    for key,members in sorted(all_groups.items(),key=lambda item:(item[0][0],order.get(item[0][1],9),item[0][1])):
        counts=collections.Counter(assign[student['row']] for student in members)
        matrix_rows.append({'teacher':key[0],'unit':key[1],'total':len(members),'counts':[counts.get(room,0) for room in range(1,number+1)]})
    room_totals=[sum(1 for student in p if assign[student['row']]==room) for room in range(1,number+1)]
    matrix={'rooms':list(range(1,number+1)),'rows':matrix_rows,'roomTotals':room_totals,'unitTotals':dict(collections.Counter(student['unit'] for student in p))}
    splits=[{'teacher':key[0],'unit':key[1],'rooms':dict(sorted(collections.Counter(assign[student['row']] for student in members).items()))} for key,members in groups.items()]
    return {'assignments':assign,'rooms':rooms,'matrix':matrix,'splits':splits,'participants':len(p),'total':number,'regular':R,'special':len(special),'dedicated':len(dedicated),'overflow':0,'quota':0,'minimal':target is None,'balanced':balanced,'splitOptimal':split_optimal,'singleDeskIdeal':ideal,'singleDesk':True,'settings':c}

def validate(book,c,a,R,kinds):
    p=book['participants'];assert set(a)=={r['row'] for r in p};assert len(kinds)<=c['limit']
    rooms=collections.defaultdict(list);groups=collections.defaultdict(set);three=set()
    for r in p:
        room=a[r['row']];rooms[room].append(r)
        if r['flags']:assert kinds[room]=={'K':'מצומצם 1','L':'מצומצם 2','M':'נפרד'}[r['flags'][0]]
        elif r['class'] in ['י7','יא7','יב7']:assert kinds[room]=='כיתה '+r['class']
        else:assert room<=R;groups[(r['teacher'],r['unit'])].add(room)
    over=0
    for room,rr in rooms.items():
        if room<=R:
            u=collections.Counter(r['unit'] for r in rr)
            if c.get('singleDesk',False):
                combined=collections.Counter(('3' if unit in ('3','3א') else unit) for r in rr for unit in [r['unit']]);assert len(rr)<=20 and max(combined.values())<=13
            else:assert len(rr)<=c['maximum'] and max(u.values())<=c['level'] and not ('3' in u and '3א' in u);over+=len(rr)>c['normal']
    assert len([r for r in rooms if r<=R])==R
    if not c.get('singleDesk',False):assert over<=math.floor(R*c['percent']/100)
    if c.get('singleDesk',False):return
    for key,rs in groups.items():
        size=sum(r['teacher']==key[0] and r['unit']==key[1] and not r['flags'] and r['class'] not in ['י7','יא7','יב7'] for r in p)
        assert len(rs)<=(2 if size<=32 else 3)
        if len(rs)==3:three.add(key[0])
    assert len(three)<=3

def restore_result(book):
    """Rebuild the displayed assignment solely from workbook column I."""
    participants=book['participants'];assignments={}
    for student in participants:
        raw=norm(student.get('assigned'))
        try:room=int(float(raw))
        except (TypeError,ValueError):raise ValueError(f"שורה {student['row']}: הקובץ נעול אך חסר מספר חדר תקין בעמודה I.")
        if room<1 or room>25:raise ValueError(f"שורה {student['row']}: מספר החדר בעמודה I מחוץ לטווח 1–25.")
        assignments[student['row']]=room
    numbers=sorted(set(assignments.values()))
    if numbers!=list(range(1,max(numbers,default=0)+1)):raise ValueError('הקובץ נעול אך מספרי החדרים בעמודה I אינם רציפים.')
    by_room=collections.defaultdict(list)
    for student in participants:by_room[assignments[student['row']]].append(student)
    kinds={};regular=[];special=[];dedicated=[];rooms=[]
    for room in numbers:
        members=by_room[room]
        flags={s['flags'][0] for s in members if s['flags']}
        classes={s['class'] for s in members if s['class'] in ['י7','יא7','יב7']}
        if flags:
            flag=next(iter(flags))
            if len(flags)!=1 or any(not s['flags'] or s['flags'][0]!=flag for s in members):raise ValueError(f'חדר {room}: שיבוץ מיוחד לא עקבי בקובץ הנעול.')
            kind={'K':'מצומצם 1','L':'מצומצם 2','M':'נפרד'}[flag];special.append(room)
        elif classes:
            dedicated_class=next(iter(classes))
            if len(classes)!=1 or any(s['class']!=dedicated_class for s in members):raise ValueError(f'חדר {room}: שיבוץ כיתה ייעודית לא עקבי בקובץ הנעול.')
            kind='כיתה '+dedicated_class;dedicated.append(room)
        else:kind='רגיל';regular.append(room)
        kinds[room]=kind;units=collections.Counter(s['unit'] for s in members)
        rooms.append({'room':room,'kind':kind,'count':len(members),'units':dict(units),'overflow':kind=='רגיל' and len(members)>29})
    groups=collections.defaultdict(list)
    for student in participants:groups[(student['teacher'],student['unit'])].append(student)
    matrix_rows=[];splits=[]
    for key,members in groups.items():
        counts=collections.Counter(assignments[s['row']] for s in members)
        matrix_rows.append({'teacher':key[0],'unit':key[1],'total':len(members),'counts':[counts.get(room,0) for room in numbers]})
        splits.append({'teacher':key[0],'unit':key[1],'rooms':dict(sorted(counts.items()))})
    matrix_rows.sort(key=lambda item:(item['teacher'],item['unit']))
    settings_value={'normal':29,'maximum':32,'percent':30,'level':16,'limit':25,'singleDesk':False,'special':{}}
    matrix={'rooms':numbers,'rows':matrix_rows,'roomTotals':[len(by_room[r]) for r in numbers],'unitTotals':dict(collections.Counter(s['unit'] for s in participants))}
    return {'assignments':assignments,'rooms':rooms,'matrix':matrix,'splits':splits,'participants':len(participants),'total':len(numbers),'regular':len(regular),'special':len(special),'dedicated':len(dedicated),'overflow':sum(r['overflow'] for r in rooms),'quota':math.floor(len(regular)*.3),'minimal':False,'balanced':False,'splitOptimal':False,'restored':True,'settings':settings_value}

def _col(n):
    out=''
    while n:
        n,r=divmod(n-1,26);out=chr(65+r)+out
    return out

def _bump_and_append(xml,section,child):
    opening=re.search(r'<'+section+r'\b[^>]*>',xml)
    closing='</'+section+'>'
    if opening is None or closing not in xml:raise ValueError('מבנה סגנונות Excel אינו נתמך: '+section)
    old=opening.group();count=re.search(r'\bcount="(\d+)"',old)
    if count:
        new=old[:count.start(1)]+str(int(count.group(1))+1)+old[count.end(1):]
        xml=xml[:opening.start()]+new+xml[opening.end():]
    return xml.replace(closing,child+closing,1)

def _matrix_styles(styles):
    xml=styles.decode('utf-8')
    counts={name:int(re.search(r'<'+name+r'\b[^>]*\bcount="(\d+)"',xml).group(1)) for name in ['fonts','fills','borders','cellXfs']}
    fonts=[
        '<font><b/><sz val="14"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>',
        '<font><b/><sz val="10"/><color rgb="FF17324D"/><name val="Arial"/></font>',
        '<font><sz val="10"/><color rgb="FF17324D"/><name val="Arial"/></font>'
    ]
    for item in fonts:xml=_bump_and_append(xml,'fonts',item)
    fills=[
        '<fill><patternFill patternType="solid"><fgColor rgb="FF163D64"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/><bgColor indexed="64"/></patternFill></fill>',
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFD9D5"/><bgColor indexed="64"/></patternFill></fill>'
    ]
    for item in fills:xml=_bump_and_append(xml,'fills',item)
    border='<border><left style="thin"><color rgb="FF7F8C99"/></left><right style="thin"><color rgb="FF7F8C99"/></right><top style="thin"><color rgb="FF7F8C99"/></top><bottom style="thin"><color rgb="FF7F8C99"/></bottom><diagonal/></border>'
    xml=_bump_and_append(xml,'borders',border)
    f0,f1,f2=counts['fonts'],counts['fonts']+1,counts['fonts']+2
    fill0,fill1,fill2,fill3=counts['fills'],counts['fills']+1,counts['fills']+2,counts['fills']+3
    border0=counts['borders']
    xfs=[
        f'<xf numFmtId="0" fontId="{f0}" fillId="{fill0}" borderId="{border0}" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        f'<xf numFmtId="0" fontId="{f1}" fillId="{fill1}" borderId="{border0}" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
        f'<xf numFmtId="0" fontId="{f2}" fillId="0" borderId="{border0}" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        f'<xf numFmtId="0" fontId="{f2}" fillId="0" borderId="{border0}" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>',
        f'<xf numFmtId="0" fontId="{f1}" fillId="{fill2}" borderId="{border0}" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>',
        f'<xf numFmtId="0" fontId="{f1}" fillId="{fill3}" borderId="{border0}" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
    ]
    for item in xfs:xml=_bump_and_append(xml,'cellXfs',item)
    ids={'title':counts['cellXfs'],'header':counts['cellXfs']+1,'body':counts['cellXfs']+2,'label':counts['cellXfs']+3,'total':counts['cellXfs']+4,'overflow':counts['cellXfs']+5}
    return xml.encode('utf-8'),ids

def _matrix_sheet(result,style):
    matrix=result['matrix'];last_col=3+len(matrix['rooms'])+2;last=_col(last_col);rows=[]
    def txt(ref,value,s):
        value=re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]','',str(value))
        return f'<c r="{ref}" s="{s}" t="inlineStr"><is><t>{html.escape(value)}</t></is></c>'
    def num(ref,value,s):return f'<c r="{ref}" s="{s}"><v>{int(value)}</v></c>'
    rows.append(f'<row r="1" ht="25" customHeight="1">{txt("A1","מטריצת שיבוץ חדרים",style["title"])}</row>')
    rows.append(f'<row r="2">{txt("A2","סה״כ נבחנים בשיבוץ",style["header"])}{num("B2",result["participants"],style["total"])}</row>')
    cells=[]
    for i,u in enumerate(['3','3א','4','5']):
        c=1+i*2;cells.extend([txt(_col(c)+'3',u+' יח״ל',style['header']),num(_col(c+1)+'3',matrix['unitTotals'].get(u,0),style['total'])])
    rows.append('<row r="3">'+''.join(cells)+'</row>')
    header=[txt('A5','שם מורה',style['header']),txt('B5','יחידות',style['header']),txt('C5','מספר תלמידים',style['header'])]
    overflow={x['room'] for x in result['rooms'] if x['overflow']}
    for i,room in enumerate(matrix['rooms'],4):header.append(num(_col(i)+'5',room,style['overflow'] if room in overflow else style['header']))
    header.extend([txt(_col(last_col-1)+'5','סה״כ',style['header']),txt(_col(last_col)+'5','בדיקה',style['header'])])
    rows.append('<row r="5" ht="30" customHeight="1">'+''.join(header)+'</row>')
    for index,item in enumerate(matrix['rows'],6):
        cells=[txt('A'+str(index),item['teacher'],style['label']),txt('B'+str(index),item['unit'],style['body']),num('C'+str(index),item['total'],style['body'])]
        for i,count in enumerate(item['counts'],4):
            if count:cells.append(num(_col(i)+str(index),count,style['body']))
            else:cells.append(txt(_col(i)+str(index),'',style['body']))
        cells.extend([num(_col(last_col-1)+str(index),sum(item['counts']),style['total']),num(_col(last_col)+str(index),item['total']-sum(item['counts']),style['total'])])
        rows.append(f'<row r="{index}">'+''.join(cells)+'</row>')
    total_row=6+len(matrix['rows']);cells=[txt('A'+str(total_row),'סה״כ',style['total']),txt('B'+str(total_row),'',style['total']),num('C'+str(total_row),result['participants'],style['total'])]
    for i,value in enumerate(matrix['roomTotals'],4):cells.append(num(_col(i)+str(total_row),value,style['overflow'] if i-3 in overflow else style['total']))
    cells.extend([num(_col(last_col-1)+str(total_row),sum(matrix['roomTotals']),style['total']),num(_col(last_col)+str(total_row),result['participants']-sum(matrix['roomTotals']),style['total'])])
    rows.append(f'<row r="{total_row}" ht="22" customHeight="1">'+''.join(cells)+'</row>')
    cols='<cols><col min="1" max="1" width="22" customWidth="1"/><col min="2" max="2" width="9" customWidth="1"/><col min="3" max="3" width="13" customWidth="1"/><col min="4" max="'+str(3+len(matrix['rooms']))+'" width="6" customWidth="1"/><col min="'+str(last_col-1)+'" max="'+str(last_col)+'" width="10" customWidth="1"/></cols>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last}{total_row}"/><sheetViews><sheetView rightToLeft="1" workbookViewId="0"><pane xSplit="3" ySplit="5" topLeftCell="D6" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'+cols+'<sheetData>'+''.join(rows)+'</sheetData>'
        f'<autoFilter ref="A5:{last}{total_row-1}"/><mergeCells count="1"><mergeCell ref="A1:{last}1"/></mergeCells>'
        '<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/></worksheet>').encode('utf-8')

def _add_matrix(data,files,result):
    wb=files['xl/workbook.xml'].decode('utf-8');rels=files['xl/_rels/workbook.xml.rels'].decode('utf-8')
    styles,style_ids=_matrix_styles(files['xl/styles.xml']);files['xl/styles.xml']=styles
    parsed=ET.fromstring(files['xl/workbook.xml']);sheet=next((s for s in parsed.findall('s:sheets/s:sheet',NS) if s.attrib.get('name')=='מטריצת שיבוץ'),None)
    if sheet is not None:
        rid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        relroot=ET.fromstring(files['xl/_rels/workbook.xml.rels']);target=next(r.attrib['Target'] for r in relroot if r.attrib.get('Id')==rid)
        sheetpath=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
    else:
        nums=[int(x) for n in files if (m:=re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml',n)) for x in [m.group(1)]];number=max(nums,default=0)+1;sheetpath=f'xl/worksheets/sheet{number}.xml'
        ridnum=max([int(x) for x in re.findall(r'\bId="rId(\d+)"',rels)],default=0)+1;rid='rId'+str(ridnum)
        sheetid=max([int(x) for x in re.findall(r'\bsheetId="(\d+)"',wb)],default=0)+1
        wb=wb.replace('</sheets>',f'<sheet name="מטריצת שיבוץ" sheetId="{sheetid}" r:id="{rid}"/></sheets>',1);files['xl/workbook.xml']=wb.encode('utf-8')
        relationship=f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{number}.xml"/>'
        rels=rels.replace('</Relationships>',relationship+'</Relationships>',1);files['xl/_rels/workbook.xml.rels']=rels.encode('utf-8')
        types=files['[Content_Types].xml'].decode('utf-8');override=f'<Override PartName="/xl/worksheets/sheet{number}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        files['[Content_Types].xml']=types.replace('</Types>',override+'</Types>',1).encode('utf-8')
    files[sheetpath]=_matrix_sheet(result,style_ids)
    return sheetpath

def write_book(data,book,result):
    assignment=result['assignments'] if 'assignments' in result else result
    text=book['text']
    for row,room in assignment.items():
        ref='I'+str(row);pat=r'<c\b(?=[^>]*\br="'+ref+r'")(?:[^>]*/>|[^>]*>.*?</c>)';m=re.search(pat,text,re.S)
        if m:
            opening=m.group().split('>')[0].rstrip('/');opening=re.sub(r'\s+t="[^"]*"','',opening)
            cell=opening+'><v>'+str(room)+'</v></c>';text=text[:m.start()]+cell+text[m.end():]
        else:
            rm=re.search(r'(<row\b[^>]*\br="'+str(row)+r'"[^>]*>)(.*?)(</row>)',text,re.S)
            if not rm:raise ValueError('לא נמצאה שורת המקור '+str(row))
            inner=rm.group(2);insert=len(inner)
            for cm in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"',inner):
                col=cm.group(1);num=0
                for ch in col:num=num*26+ord(ch)-64
                if num>9:insert=cm.start();break
            inner=inner[:insert]+f'<c r="{ref}"><v>{room}</v></c>'+inner[insert:];text=text[:rm.start(2)]+inner+text[rm.end(2):]
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        files={item.filename:src.read(item.filename) for item in src.infolist()}
        infos={item.filename:item for item in src.infolist()}
    files[book['path']]=text.encode()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dst:
        for name,b in files.items():dst.writestr(infos.get(name,name),b)
    output=out.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as src,zipfile.ZipFile(io.BytesIO(output)) as dst:
        assert set(src.namelist()).issubset(dst.namelist())
        allowed={book['path']}
        for n in src.namelist():
            if n not in allowed:assert src.read(n)==dst.read(n)
            if n.endswith('vbaProject.bin'):assert src.read(n)==dst.read(n)
        before=ET.fromstring(src.read(book['path']));after=ET.fromstring(dst.read(book['path']))
        for tree in [before,after]:
            for row in tree.findall('s:sheetData/s:row',NS):
                for cell in list(row):
                    if cell.attrib.get('r') in {'I'+str(n) for n in assignment}:row.remove(cell)
        assert ET.tostring(before)==ET.tostring(after)
        cells={c.attrib['r']:c for c in ET.fromstring(dst.read(book['path'])).iter(tag('c'))}
        assert all(int(cells['I'+str(r)].find('s:v',NS).text)==v for r,v in assignment.items())
    return output
