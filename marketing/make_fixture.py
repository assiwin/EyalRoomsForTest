from openpyxl import Workbook
from pathlib import Path
import json
p=Path('marketing/capture');p.mkdir(parents=True,exist_ok=True)
w=Workbook();s=w.active;s.title='dbase'
s.append(['תעודת זהות','שם תלמיד','כיתה','תוספת זמן','הגדלה','הקראה','מורה','יחידות','חדר','משתתף','עתידי','מצומצם','נפרד','בעיה'])
first=['אור','נועה','איתי','תמר','עידו','מאיה','דניאל','שירה','יובל','רוני','אדם','יעל']
last=['כהן','לוי','ישראלי','שחר','ברק','גפן','אורן','דגן','לביא','רימון','קדם','שדה']
teachers=['דנה כהן','אורי לוי','רותם שחר','יעל ברק','איתי גפן','מיה אורן','רון דגן','טל לביא']
for i in range(240):
 reduced=216<=i<222;separate=222<=i<225;dedicated=i>=225
 group=min(i//27,7);unit=['3','3א','4','5','3','4','5','3'][group]
 if reduced:unit='4' if i%2 else '5'
 if dedicated:unit='3'
 name=first[i%12]+' '+last[(i//12)%12]+' '+str(i//144+1)
 s.append([str(900000001+i),name,'יא7' if dedicated else 'יא'+str(i%6+1), '50' if reduced else '', 'כן' if i%43==0 else '', 'כן' if i%51==0 else '',teachers[group] if not dedicated else 'ניצן פלג',unit,'',1,'',int(reduced),int(separate),''])
w.create_sheet('ניהול');w.save(p/'demo_classlist.xlsx')
print('Created 240 synthetic students')
