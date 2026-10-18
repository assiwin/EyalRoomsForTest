from pathlib import Path
import subprocess,json,math,re,wave
import numpy as np
ROOT=Path(__file__).resolve().parent;A=ROOT/'assets'
SR=48000;D=78;T=[0,9,17,26,37,47,60,68,78]
def probe(f):return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(f)]))
N=SR*D;mix=np.zeros((N,2),dtype=np.float32);voiceenv=np.zeros(N,dtype=np.float32)
texts=json.loads((A/'narration.json').read_text(encoding='utf-8'));captions=[]
for i in range(8):
 f=A/f'voice-{i}.mp3';dur=probe(f);slot=T[i+1]-T[i];rate=max(1,dur/(slot-.65));out=A/f'voice-ready-{i}.wav'
 subprocess.run(['ffmpeg','-y','-i',str(f),'-af',f'atempo={rate},highpass=f=70,loudnorm=I=-18:TP=-2:LRA=8','-ar',str(SR),'-ac','2','-c:a','pcm_s16le',str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
 with wave.open(str(out)) as w:v=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).reshape(-1,2).astype(np.float32)/32768
 start=int((T[i]+.28)*SR);end=min(N,start+len(v));mix[start:end]+=v[:end-start];voiceenv[max(0,start-int(.1*SR)):min(N,end+int(.12*SR))]=1
 chunks=[x.strip() for x in re.split(r'(?<=[.!?])\s+',texts[i]) if x.strip()]
 ct=T[i]+.28;total=sum(len(x) for x in chunks);length=len(v)/SR
 for c in chunks:
  cd=length*len(c)/total;captions.append({'start':ct,'end':ct+cd,'text':c});ct+=cd
 print(i,'rate',round(rate,2),'seconds',round(length,2))
# Original electronic underscore: soft keys, bass pulse, restrained percussion.
music=np.zeros((N,2),dtype=np.float32);bpm=104;beat=60/bpm;bar=4*beat
chords=[[50,54,57,61],[47,50,54,57],[43,47,50,54],[45,49,52,57]]
def add(t,dur,freq,amp,pan=0,kind='pluck'):
 st=int(t*SR);n=min(int(dur*SR),N-st)
 if n<=0:return
 tt=np.arange(n)/SR
 if kind=='pad':
  env=np.minimum(tt/.3,1)*np.minimum((dur-tt)/.5,1);v=(np.sin(2*np.pi*freq*tt)+.22*np.sin(2*np.pi*freq*2*tt))*env*.4
 elif kind=='bass':v=np.sin(2*np.pi*freq*tt)*np.exp(-tt*2.5)*np.minimum(tt/.015,1)
 else:v=(np.sin(2*np.pi*freq*tt)+.28*np.sin(2*np.pi*freq*2*tt)+.1*np.sin(2*np.pi*freq*3*tt))*np.exp(-tt*5)*np.minimum(tt/.008,1)
 music[st:st+n,0]+=v*amp*(1-pan*.35);music[st:st+n,1]+=v*amp*(1+pan*.35)
for bi in range(math.ceil(D/bar)):
 base=bi*bar;chord=chords[bi%4]
 for m in chord:add(base,bar+.3,440*2**((m+12-69)/12),.018,kind='pad')
 for k in range(8):
  note=chord[[0,2,1,3,0,2,3,1][k]]+24;add(base+k*beat/2,1.0,440*2**((note-69)/12),.026,pan=(-1 if k%2 else 1))
 for k in range(4):add(base+k*beat,.5,440*2**((chord[0]-12-69)/12),.038,kind='bass')
 # filtered shaker, gentle kick
 for k in range(8):
  st=int((base+k*beat/2)*SR);n=min(int(.06*SR),N-st)
  if n<=0:continue
  rng=np.random.default_rng(bi*8+k);noise=rng.normal(0,1,n);noise=noise-np.convolve(noise,np.ones(5)/5,mode='same');v=noise*np.exp(-np.arange(n)/SR*65)*.004
  music[st:st+n]+=v[:,None]
# smooth ducking under speech
from scipy.ndimage import gaussian_filter1d
small=voiceenv[::480];smoothed=gaussian_filter1d(small,sigma=7);duck=np.interp(np.arange(N)/480,np.arange(len(smoothed)),smoothed)
music*=((1-.5*duck)*np.minimum(np.arange(N)/SR/2,1)*np.minimum((D-np.arange(N)/SR)/2,1))[:,None]
mix+=music
# subtle transition chime
for at in T[1:-1]:
 st=int(at*SR);n=min(int(.35*SR),N-st);t=np.arange(n)/SR;v=.015*np.sin(2*np.pi*(880*t+150*t*t))*np.exp(-t*13);mix[st:st+n]+=v[:,None]
peak=np.max(np.abs(mix));mix*=min(1,.92/peak)
with wave.open(str(A/'soundtrack-78s.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((np.clip(mix,-1,1)*32767).astype(np.int16).tobytes())
subprocess.run(['ffmpeg','-y','-i',str(A/'soundtrack-78s.wav'),'-af','atempo=1.04','-t','75',str(A/'soundtrack.wav')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
(A/'captions.json').write_text(json.dumps(captions,ensure_ascii=False),encoding='utf-8')
print('Audio ready')
