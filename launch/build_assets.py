"""Build original launch audio and genuine demo-derived graphics. No network calls."""
from pathlib import Path
import json, math, wave, hashlib
import numpy as np
from html import escape
ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'composition/assets'
ASSETS.mkdir(parents=True,exist_ok=True)
DEMO=ROOT.parent/'src/qloom/data/demo.json'
report=json.loads(DEMO.read_text())
best=next(c for c in report['candidates'] if c['id']==report['best_id'])
summary={'source':'src/qloom/data/demo.json','source_sha256':hashlib.sha256(DEMO.read_bytes()).hexdigest(),'input':report['input']['name'],'device':report['device']['name'],'budget':report['budget'],'configurations':24,'best_id':report['best_id'],'max_error':best['verification']['max_error'],'initial_mapping':best['initial_mapping'],'final_mapping':best['final_mapping'],'metrics':best['metrics'],'history':best['history'],'edges':report['device']['edges'],'n_qubits':report['input']['n_qubits']}
(ASSETS/'demo-evidence.json').write_text(json.dumps(summary,indent=2)+'\n')
# Complete prefix of the real input. The word "excerpt" stays on screen.
ops=report['input']['operations'][:24];n=report['input']['n_qubits'];W=1140;H=310;gap=50
levels=[0]*n;positioned=[]
for op in ops:
    lo,hi=min(op['qubits']),max(op['qubits']);col=max(levels[lo:hi+1]);levels[lo:hi+1]=[col+1]*(hi-lo+1);positioned.append((op,col))
step=min(62,1000/max(1,max(levels)))
b=''
for q in range(n):
    y=46+q*gap
    b+=f'<text x="7" y="{y+5}" fill="#758084" font-family="monospace" font-size="16">q{q}</text><path d="M60 {y}H1120" stroke="#cfd7d2" stroke-width="1.5"/>'
for op,col in positioned:
    x=95+col*step;ys=[46+q*gap for q in op['qubits']];g=op['gate']
    b+=f'<g><title>{escape(g+str(op["qubits"]))}</title>'
    if g=='cx':
        b+=f'<path d="M{x} {ys[0]}V{ys[1]}" stroke="#bc7e35" stroke-width="2"/><circle cx="{x}" cy="{ys[0]}" r="5" fill="#bc7e35"/><circle cx="{x}" cy="{ys[1]}" r="12" fill="#f3f2ec" stroke="#bc7e35" stroke-width="2"/><path d="M{x-7} {ys[1]}h14M{x} {ys[1]-7}v14" stroke="#bc7e35" stroke-width="2"/>'
    else:
        b+=f'<rect x="{x-17}" y="{ys[0]-17}" width="34" height="34" rx="3" fill="#fffefa" stroke="#547b8e" stroke-width="1.5"/><text x="{x}" y="{ys[0]+5}" text-anchor="middle" fill="#315d7a" font-family="monospace" font-size="14">{escape(g.upper())}</text>'
    b+='</g>'
(ASSETS/'actual-circuit.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><title>Actual {escape(report["input"]["name"])} input prefix: first {len(ops)} operations</title>{b}</svg>')
# Original ambient score. Four diatonic voicings, low amplitude, no samples.
sr=22050;duration=20;t=np.arange(sr*duration)/sr
left=np.zeros_like(t);right=np.zeros_like(t)
chords=[(110,164.8138,220,261.6256,329.6276),(87.3071,130.8128,174.6141,220,261.6256),(130.8128,195.9977,261.6256,329.6276,391.9954),(97.9989,146.8324,195.9977,246.9417,293.6648)]
for ci,chord in enumerate(chords):
    start=ci*5;local=t-start;mask=(local>=0)&(local<5.7);lt=np.maximum(local,0)
    envelope=np.clip(lt/1.5,0,1)*np.clip((5.7-lt)/1.7,0,1)*mask
    for ni,freq in enumerate(chord):
        amp=.016/(1+.15*ni)
        left+=amp*envelope*(np.sin(2*np.pi*freq*lt)+.13*np.sin(2*np.pi*freq*2*lt))
        right+=amp*envelope*(np.sin(2*np.pi*freq*lt+.045*(ni+1))+.13*np.sin(2*np.pi*freq*2*lt+.1))
# Restrained original plucks accent the three scene handoffs.
for moment,freq in [(4,523.2511),(10,659.2551),(16,391.9954)]:
    local=t-moment;mask=(local>=0)&(local<1.5);lt=np.maximum(local,0)
    env=(1-np.exp(-lt*100))*np.exp(-lt*3.8)*mask*.055
    signal=env*(np.sin(2*np.pi*freq*lt)+.18*np.sin(2*np.pi*freq*2*lt))
    left+=signal;right+=signal*.9
fade=np.minimum(1,t/.6)*np.minimum(1,(duration-t)/1.2)
stereo=np.stack([left*fade,right*fade],axis=1)
peak=float(np.max(np.abs(stereo)))
with wave.open(str(ASSETS/'original-score.wav'),'wb') as out:
    out.setnchannels(2);out.setsampwidth(2);out.setframerate(sr);out.writeframes((np.clip(stereo,-1,1)*32767).astype('<i2').tobytes())
mono=stereo.mean(axis=1);rms=[]
for frame in range(duration*30):
    chunk=mono[int(frame*sr/30):int((frame+1)*sr/30)];rms.append(float(np.sqrt(np.mean(chunk**2))))
scale=max(rms) or 1
(ASSETS/'audio-rms.js').write_text('window.QLOOM_AUDIO_RMS='+json.dumps([round(x/scale,5) for x in rms])+';\n')
(ASSETS/'audio-evidence.json').write_text(json.dumps({'original':True,'sample_rate':sr,'channels':2,'duration_s':duration,'peak_linear':peak,'peak_dbfs':20*math.log10(peak),'rms_frames':len(rms),'fps':30,'authored_cues_s':[4,10,16]},indent=2)+'\n')
print(json.dumps({'report':summary['input'],'budget':summary['budget'],'residual':summary['max_error'],'audio_peak_dbfs':20*math.log10(peak)},indent=2))
