from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from pathlib import Path
import numpy as np, math, json, subprocess, os, sys
from functools import lru_cache
ROOT=Path(__file__).resolve().parent
A=ROOT/'assets'; OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
W,H,FPS,DURATION=1920,1080,30,78
FINAL_DURATION=75
TIMES=[0,9,17,26,37,47,60,68,78]
NAVY='#091B30';TEAL='#52DBC3';WHITE='#F6FAFF';MUTED='#B0C8D8'
FONT=A/'Heebo.ttf'
if not FONT.exists():FONT=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
@lru_cache(maxsize=100)
def font(size,weight=500):
 f=ImageFont.truetype(str(FONT),size)
 try:f.set_variation_by_axes([weight])
 except:pass
 return f

def text(im,s,x,y,size=50,fill=WHITE,weight=500,anchor='ra'):
 d=ImageDraw.Draw(im);d.text((x,y),s,font=font(size,weight),fill=fill,anchor=anchor,direction='rtl' if any('\u0590'<=c<='\u05ff' for c in s) else 'ltr',stroke_width=0)

def ease(v):v=max(0,min(1,v));return 1-(1-v)**3

def bg(t):
 im=BG.copy();d=ImageDraw.Draw(im)
 for j in range(7):
  x=100+j*293+int(8*math.sin(t*.18+j));d.line([(x,0),(x,H)],fill=(18,43,62),width=1)
 # subtle moving orbital curves
 for k in range(3):
  r=280+k*58;d.ellipse((-r+270,-r+H+90,r+270,r+H+90),outline=(20,56,73),width=2)
 return im

yy,xx=np.mgrid[0:H,0:W];glow=np.exp(-(((xx-350)/1100)**2+((yy-400)/950)**2))
arr=np.zeros((H,W,3),dtype=np.uint8)
for i,(b,v) in enumerate([(7,11),(20,28),(36,33)]):arr[:,:,i]=(b+v*glow).astype(np.uint8)
BG=Image.fromarray(arr)

def pill(im,label,x,y,width=340,color=TEAL):
 d=ImageDraw.Draw(im);d.rounded_rectangle((x-width,y,x,y+52),radius=26,fill='#123B49',outline='#266354',width=1)
 text(im,label,x-width/2,y+27,26,color,600,'mm')

def heading(im,kicker,lines,sub,entrance=1):
 shift=50*(1-entrance)
 text(im,kicker,1830+shift,210,24,TEAL,700)
 for k,line in enumerate(lines):text(im,line,1830+shift,285+k*90,74,WHITE,750)
 if sub:
  for k,line in enumerate(sub):text(im,line,1830+shift,505+k*46,30,MUTED,400)
 d=ImageDraw.Draw(im);d.rounded_rectangle((1750,170,1830,175),radius=2,fill=TEAL)

IMAGES={}
def load(name):
 if name not in IMAGES:IMAGES[name]=Image.open(A/name).convert('RGB')
 return IMAGES[name]

def card(im,img,x=65,y=260,width=1130,scale=1):
 # product screen in a restrained presentation frame
 height=int(width*img.height/img.width)
 d=ImageDraw.Draw(im)
 d.rounded_rectangle((x+8,y+16,x+width+8,y+height+16),radius=24,fill='#04101E')
 d.rounded_rectangle((x-3,y-38,x+width+3,y+height+3),radius=22,fill='#294256')
 d.rectangle((x-3,y-8,x+width+3,y+height-16),fill='#294256')
 for i,c in enumerate(['#FF9C91','#E3C46C','#60C9AD']):d.ellipse((x+19+i*20,y-24,x+28+i*20,y-15),fill=c)
 text(im,'סדרן חדרים',x+width-20,y-18,18,'#CBE0EB',500,'rm')
 im.paste(img.resize((width,height),Image.Resampling.LANCZOS),(int(x),int(y)))

def screen(im,name,p=0,top=250,width=1140):
 img=load(name)
 # subtle continuous dolly in
 zoom=1+.025*p;cw=int(img.width/zoom);ch=int(img.height/zoom)
 x0=(img.width-cw)//2;y0=(img.height-ch)//2
 img=img.crop((x0,y0,x0+cw,y0+ch))
 card(im,img,65,top,width)

def brand(im,x=1820,y=75):
 icon=load('app_icon.png').convert('RGBA').resize((54,54),Image.Resampling.LANCZOS)
 im.paste(icon,(int(x-54),int(y-27)),icon)
 text(im,'סדרן חדרים',x-72,y,30,WHITE,700)

def bottom(im,t,scene):
 d=ImageDraw.Draw(im)
 d.rectangle((70,1025,1850,1027),fill='#294254')
 d.rectangle((70,1025,70+int(1780*t/DURATION),1027),fill=TEAL)
 if 1<=scene<=6:text(im,'הדגמה עם נתונים סינתטיים',1850,995,20,'#7B9EAF',400)
 # Optional, synchronized captions; restrained two-line band.
 if CAPTIONS:
  cap=next((c['text'] for c in CAPTIONS if c['start']<=t<c['end']),None)
  if cap:
   lines=wrap(cap,1450,31)
   height=48*len(lines)+22;box=(170,950-height,1750,950)
   layer=Image.new('RGBA',(W,H));ld=ImageDraw.Draw(layer);ld.rounded_rectangle(box,radius=14,fill=(3,12,22,210));im.paste(layer,(0,0),layer)
   for i,line in enumerate(lines):text(im,line,960,950-height+30+i*45,31,WHITE,500,'mm')

def wrap(s,width,size):
 words=s.split();lines=[];cur=''
 for word in words:
  v=(cur+' '+word).strip()
  if font(size).getlength(v)>width and cur:lines.append(cur);cur=word
  else:cur=v
 if cur:lines.append(cur)
 return lines

rng=np.random.default_rng(52)
SCATTER=rng.uniform([70,300],[1150,800],size=(60,2));TARGET=np.array([[120+(i%10)*104,330+(i//10)*78] for i in range(60)])

def papers(im,p):
 names=['pdf-matrix.png','pdf-envelope.png','pdf-teacher.png']
 centers=[(300,575),(660,560),(1010,575)];angles=[8,0,-8]
 for idx,(name,center,a) in enumerate(zip(names,centers,angles)):
  pic=load(name);pic.thumbnail((370,550),Image.Resampling.LANCZOS)
  border=Image.new('RGB',(pic.width+16,pic.height+16),'white');border.paste(pic,(8,8))
  q=border.convert('RGBA').rotate(a*(1-.2*p),resample=Image.Resampling.BICUBIC,expand=True)
  dy=int(45*(1-ease((p*2-idx*.15))))
  im.paste(q,(int(center[0]-q.width/2),int(center[1]-q.height/2+dy)),q)

CLIPS={}
def clip_image(name,p):
 files=CLIPS.get(name)
 if files is None:files=sorted((A/name).glob('*.jpg'));CLIPS[name]=files
 if not files:return None
 return Image.open(files[min(len(files)-1,int(p*len(files)))]).convert('RGB')

def scene(n,u,t):
 dur=TIMES[n+1]-TIMES[n];p=max(0,min(1,u/dur));en=ease(u/1.0)
 im=bg(t);brand(im)
 if n==0:
  text(im,'יום בחינה מתחיל הרבה לפני הצלצול.',1830,205,28,TEAL,600)
  for k,line in enumerate(['מאות תלמידים.','יום בחינה אחד.']):text(im,line,1830,325+k*110,88,WHITE,750)
  text(im,'מי יושב איפה?',1830,610,56,TEAL,600)
  q=ease((u-2.5)/3.5);d=ImageDraw.Draw(im)
  for i,(a,b) in enumerate(zip(SCATTER,TARGET)):
   x,y=(1-q)*a+q*b;d.rounded_rectangle((x,y,x+74,y+49),radius=11,fill=('#1A6A72' if i%7==0 else '#214A61'),outline='#3C8190',width=1)
   d.ellipse((x+30,y+9,x+44,y+23),fill=TEAL if i%7==0 else '#A7C5D6');d.rounded_rectangle((x+22,y+27,x+52,y+39),radius=6,fill=TEAL if i%7==0 else '#A7C5D6')
  pill(im,'תלמידים · התאמות · מורים · חדרים',1150,205,710)
 elif n==1:
  heading(im,'הכירו את סדרן חדרים',['מהנתונים','לתוכנית עבודה.'],['סביבת עבודה ברורה','לרכזי בחינות.'],en)
  screen(im,'02-dashboard.png',p)
  pill(im,'תהליך אחד. תמונה שלמה.',1180,170,440)
 elif n==2:
  heading(im,'מתחילים בנתונים',['הנתונים שלכם.','השליטה שלכם.'],['קובצי Excel, שכבת מבחן','והגדרות במקום אחד.'],en)
  if p<.47:screen(im,'01-database.png',p)
  else:screen(im,'02-dashboard.png',p)
  for i,(label,w) in enumerate([('קובצי Excel',260),('התאמות',220),('זמני בחינה',250)]):pill(im,label,1830,650+i*72,w)
 elif n==3:
  heading(im,'שיבוץ שמבוסס על הכללים שלכם',['מורכבות גדולה.','תמונה ברורה.'],['מטריצת מורים וחדרים','ותוצאות שאפשר לבחון.'],en)
  pic=load('results-element.png')
  # Show the summary + complete matrix, excluding the collapsed technical details.
  pic=pic.crop((0,260,pic.width,812))
  card(im,pic,110,185,1020)
  pill(im,f"{META['students']} תלמידים בהדגמה",1830,650,380)
  pill(im,f"{META['rooms']} חדרים בתוצאה",1830,725,380)
 elif n==4:
  heading(im,'גמישות כשהתוכנית משתנה',['מספר החדרים','השתנה?'],['מחשבים מחדש ומאזנים.','אתם בוחנים את התוצאה.'],en)
  pic=load('05-adjust.png').crop((125,285,995,615));card(im,pic,65,320,1140)
  d=ImageDraw.Draw(im);d.rounded_rectangle((1370,670,1830,790),radius=24,fill='#123B49',outline='#2B726B',width=2)
  text(im,'הוספה  +',1730,730,40,TEAL,650,'mm');text(im,'−  הפחתה',1480,730,40,WHITE,650,'mm')
 elif n==5:
  heading(im,'מגיעים מוכנים ליום הבחינה',['מהשיבוץ','ישר לשטח.'],['דוחות למורים ומעטפות,','רשימת הקראה וסידורי ישיבה.'],en)
  if p<.30:
   pic=clip_image('map-clip',min(1,p/.30))
   if pic is None:pic=load('06-roommap.png')
   card(im,pic,65,245,1140)
  else:papers(im,(p-.30)/.70)
  pill(im,'תוצרים אמיתיים מתוך ההדגמה',1180,170,530)
 elif n==6:
  heading(im,'כל הפרטים מתחברים',['התלמידים שובצו.','הצוות יודע לאן.'],['תמונה ברורה לרכז.','מידע מסודר לצוות.'],en)
  pic=load('pdf-seating.png');pic.thumbnail((940,670),Image.Resampling.LANCZOS)
  d=ImageDraw.Draw(im);x=620-pic.width//2;y=180;d.rounded_rectangle((x-8,y-8,x+pic.width+8,y+pic.height+8),radius=10,fill='white');im.paste(pic,(x,y))
  pill(im,'סידורי ישיבה לפי חדר',1830,670,410)
 elif n==7:
  # Closing hero deliberately uses spacious typography and one call to action.
  icon=load('app_icon.png').convert('RGBA').resize((112,112),Image.Resampling.LANCZOS);im.paste(icon,(904,150),icon)
  text(im,'סדרן חדרים',960,330,80,WHITE,750,'mm')
  text(im,'יותר סדר בהכנה.',960,462,70,WHITE,650,'mm')
  text(im,'יותר שליטה ביום הבחינה.',960,555,70,TEAL,650,'mm')
  text(im,'שיבוץ חדרים  ·  התאמות  ·  דוחות  ·  סידורי ישיבה',960,665,31,MUTED,400,'mm')
  q=ease((u-.8)/.7);d=ImageDraw.Draw(im);d.rounded_rectangle((730,742+int(20*(1-q)),1190,835+int(20*(1-q))),radius=46,fill=TEAL)
  text(im,'בקשו הדגמה',960,790+int(20*(1-q)),40,NAVY,750,'mm')
 bottom(im,t,n)
 return im

META=json.loads((A/'demo-meta.json').read_text()) if (A/'demo-meta.json').exists() else {'students':240,'rooms':11}
CAPTIONS=json.loads((A/'captions.json').read_text()) if (A/'captions.json').exists() else []
def frame(t):
 n=next(i for i in range(8) if TIMES[i]<=t<TIMES[i+1]);u=t-TIMES[n];im=scene(n,u,t)
 if n>0 and u<.45:im=Image.blend(scene(n-1,TIMES[n]-TIMES[n-1]-.001,t),im,ease(u/.45))
 return im

if __name__=='__main__':
 if '--preview' in sys.argv:
  for t in [3,10,18,29,41,54,63,71]:frame(t).save(OUT/f'preview-{t}.jpg',quality=94)
  thumbs=[]
  for t in [3,10,18,29,41,54,63,71]:thumbs.append(Image.open(OUT/f'preview-{t}.jpg').resize((640,360)))
  sheet=Image.new('RGB',(1280,1440))
  for i,q in enumerate(thumbs):sheet.paste(q,((i%2)*640,(i//2)*360))
  sheet.save(OUT/'contact-sheet.jpg');print('Preview ready')
 else:
  cmd=['ffmpeg','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(A/'soundtrack.wav'),'-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(FINAL_DURATION),str(OUT/'SadranRooms_Marketing_v27_75s.mp4')]
  proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=open(OUT/'encode.log','w'))
  try:
   for i in range(FPS*FINAL_DURATION):
    proc.stdin.write(frame(i/FPS*DURATION/FINAL_DURATION).tobytes())
    if i%300==0:print('Rendered',i,'/',FPS*FINAL_DURATION,flush=True)
  finally:proc.stdin.close()
  code=proc.wait();print('ENCODE',code);sys.exit(code)
