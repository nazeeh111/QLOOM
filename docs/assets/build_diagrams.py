"""Create editable QLOOM vector masters from the documented source architecture."""
from pathlib import Path
from html import escape

HERE=Path(__file__).resolve().parent
C={'canvas':'#f3f2ec','surface':'#fffefa','ink':'#203239','muted':'#647277','line':'#cfd6cf','blue':'#315d7a','amber':'#bc7e35','green':'#387455'}

def text(x,y,value,size=16,color='ink',weight=400,anchor='start',font='sans-serif',id=None):
    return f'<text {f"id={chr(34)+id+chr(34)}" if id else ""} x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" fill="{C.get(color,color)}" text-anchor="{anchor}">{escape(str(value))}</text>'
def line(x1,y1,x2,y2,color='line',width=2,dash='',arrow=False):
    return f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{C.get(color,color)}" stroke-width="{width}" fill="none" {f"stroke-dasharray={chr(34)+dash+chr(34)}" if dash else ""} {"marker-end=\"url(#arrow)\"" if arrow else ""}/>'
def box(id,x,y,w,h,title,lines,tone='blue',tag=None):
    s=f'<g id="{id}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{C["surface"]}" stroke="{C["line"]}"/><rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{C[tone]}"/>'
    s+=text(x+20,y+30,title,18,weight=600)
    for i,l in enumerate(lines):s+=text(x+20,y+57+i*23,l,13,'muted')
    if tag:s+=text(x+w-15,y+29,tag,10,tone,anchor='end',font='monospace')
    return s+'</g>'
def base(w,h,title,description,body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title description"><title id="title">{escape(title)}</title><desc id="description">{escape(description)}</desc><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" fill="none" stroke="{C["blue"]}" stroke-width="1.3"/></marker></defs><rect width="{w}" height="{h}" fill="{C["canvas"]}"/>{body}</svg>'
def mark(x,y,s=1):
    return f'<g transform="translate({x} {y}) scale({s})" fill="none" stroke="{C["blue"]}" stroke-width="2.6"><path d="M5 10h18c7 0 7 20 14 20M5 20h30M5 30h18c7 0 7-20 14-20"/><path d="M12 4v32M22 4v32" stroke="{C["amber"]}"/></g>'

b=mark(43,36,1.3)+text(105,76,'QLOOM',39,weight=700)+text(1280,68,'SYSTEM ARCHITECTURE / v0.1',13,'muted',anchor='end',font='monospace')
b+=text(50,134,'Learn where to search. Verify what you find.',32,weight=500)
b+=text(50,165,'Offline learning and online compilation are distinct. Logical verification is independent of noise evaluation.',16,'muted')
b+='<g id="offline-lane"><rect x="35" y="195" width="1295" height="225" rx="10" fill="#e9ede7"/>'
b+=text(55,224,'01  OFFLINE / REPRODUCIBLE TRAINING',12,'muted',font='monospace')
b+=box('training-evaluations',55,245,300,148,'Real compiler evaluations',['Generated training circuits × devices','All 24 native configurations','Verified cost labels, no test labels'])
b+=box('graph-features',385,245,265,148,'Graph-aware features',['Circuit interaction statistics','Topology and placement distances','Configuration descriptors'])
b+=box('model-fit',680,245,285,148,'ExtraTrees regression',['Fit normalized hardware cost','Training seeds and source retained','Compact, CPU-compatible model'])
b+=box('json-model',995,245,310,148,'Frozen JSON model',['Tree arrays, feature order, metadata','Content hash in each report','No executable pickle artifact'],tone='amber')
b+=line(356,319,382,319,'blue',arrow=True)+line(651,319,677,319,'blue',arrow=True)+line(966,319,992,319,'blue',arrow=True)+'</g>'
b+=text(55,466,'02  ONLINE / A BOUNDED COMPILATION EXPERIMENT',12,'muted',font='monospace')
b+=box('input-validation',55,490,260,145,'Circuit + processor',['OpenQASM 2 / Python circuit','2–8 qubits; terminal measurement','Connected, synthetic U/CX device'])
b+=box('budgeted-ranking',350,490,285,145,'Rank 24 configurations',['Frozen model scores graph features','Select only the requested budget','Default demonstration: 4 evaluations'])
b+=box('native-compiler',670,490,300,145,'QLOOM native compiler',['Commuting inverse / rotation rewrites','Interaction-aware initial placement','Shortest / lookahead SWAP routing'])
b+=box('semantics-gate',1005,490,300,145,'Independent semantics gate',['NumPy interpreter, full unitary','Initial / final logical mappings','Global phase + random input checks'],tone='green')
b+=line(316,562,347,562,'blue',arrow=True)+line(636,562,667,562,'blue',arrow=True)+line(971,562,1002,562,'blue',arrow=True)
b+='<path id="model-to-ranking" d="M1150 394V444H492V487" stroke="#bc7e35" stroke-width="2" stroke-dasharray="5 5" fill="none" marker-end="url(#arrow)"/>'
b+='<path id="verified-only" d="M1155 637V680H1065V716" stroke="#315d7a" stroke-width="2" fill="none" marker-end="url(#arrow)"/>'
b+=text(1140,669,'passed only',11,'green',anchor='end',font='monospace')
b+=box('hardware-evaluation',855,720,450,138,'Hardware cost + optional noise',['CX count, depth, duration, cost proxy, measured wall time','Aer density matrix: simulated output distributions','Noisy similarity never serves as equivalence proof'],tone='amber')
b+=box('studio-export',350,720,450,138,'Inspectable Studio + reproducible export',['Candidate records, routing replay, Pareto frontier','OpenQASM + mappings + global phase sidecar','Complete experiment report and baseline evidence'])
b+=line(852,789,803,789,'blue',arrow=True)
b+=box('baselines',55,720,260,138,'Established baselines',['Qiskit optimization levels 0–3','MQT QMAP and BQSKit','Same width, gates and coupling'])
b+='<path id="baseline-evaluation" d="M185 861V894H1080V861" stroke="#315d7a" stroke-width="1.7" stroke-dasharray="4 4" fill="none" marker-end="url(#arrow)"/>'
b+=text(425,916,'Baselines have independently checked semantics and separately reported compilation effort.',13,'muted')
b+=line(50,950,1305,950)+text(50,980,'SCOPE  Unitary circuits + terminal measurements · no ancillas, resets, dynamic control or real QPU execution',12,'muted',font='monospace')
(HERE/'architecture.svg').write_text(base(1360,1010,'QLOOM compiler architecture','Offline graph-aware surrogate training ranks configurations for a hard-budget native compiler. Independent phase-and-mapping verification precedes hardware metrics, optional noise simulation, Studio inspection and export.',b))

b=mark(67,55,2)+text(164,116,'QLOOM',67,weight=730)+text(70,185,'QUANTUM COMPILER STUDIO',15,'muted',font='monospace')
b+=text(70,285,'Weave a better',66,weight=500)+text(70,360,'quantum circuit.',66,weight=500)
b+=text(73,421,'Learned search. Explicit mappings. Independent verification.',21,'muted')
b+=text(73,548,'github.com/nazeeh111/QLOOM',17,'blue',font='monospace')
for i in range(5):
    y=145+i*72
    b+=line(805,y,1195,y,'line',1.5)+text(770,y+4,f'q{i}',13,'muted',font='monospace')
for x,qs in [(856,[0,3]),(953,[1,4]),(1104,[0,2])]:
    ys=[145+q*72 for q in qs];b+=line(x,ys[0],x,ys[1],'amber',2)
    b+=f'<circle cx="{x}" cy="{ys[0]}" r="6" fill="{C["amber"]}"/><circle cx="{x}" cy="{ys[1]}" r="14" fill="{C["canvas"]}" stroke="{C["amber"]}" stroke-width="2"/>'+line(x-8,ys[1],x+8,ys[1],'amber',2)+line(x,ys[1]-8,x,ys[1]+8,'amber',2)
for x,q in [(808,0),(906,2),(1000,1),(1148,4)]:
    y=145+q*72;b+=f'<rect x="{x-16}" y="{y-16}" width="32" height="32" rx="3" fill="{C["surface"]}" stroke="{C["blue"]}"/>'+text(x,y+5,'U',14,'blue',anchor='middle',font='monospace')
b+=text(809,548,'LOCAL CPU · SIMULATED HARDWARE',12,'muted',font='monospace')
(HERE/'social-preview.svg').write_text(base(1280,640,'QLOOM Quantum Compiler Studio','Original QLOOM brand with an illustrative circuit motif. Learned search, explicit mappings and independent verification.',b))

b=mark(0,0,3)+text(132,92,'QLOOM',86,weight=730)
(HERE/'logo.svg').write_text(base(530,125,'QLOOM wordmark','Original woven quantum path emblem and QLOOM wordmark.',b))
