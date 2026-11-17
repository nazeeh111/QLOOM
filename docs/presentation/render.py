from pathlib import Path
import json,hashlib,sys,re
import xml.etree.ElementTree as ET
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Circle
R=Path(__file__).resolve().parents[2]
MOBILE='--mobile' in sys.argv
plt.rcParams.update({'font.family':['DejaVu Sans','Arial','sans-serif'],'font.size':15,'axes.spines.top':False,'axes.spines.right':False,'axes.labelsize':15,'xtick.labelsize':13,'ytick.labelsize':13,'svg.fonttype':'none','figure.facecolor':'#ffffff','axes.facecolor':'#ffffff','text.color':'#172b3a','axes.labelcolor':'#172b3a','xtick.color':'#334a5b','ytick.color':'#334a5b','axes.edgecolor':'#8a9aa7'})
manifest={'method':'Matplotlib source-derived figures from exact retained JSON; no solver, inference, new experiment, image enhancement or smoothing','runtime':{'python':sys.version,'matplotlib':matplotlib.__version__,'numpy':np.__version__},'font_policy':['DejaVu Sans','Arial','sans-serif'],'figures':[]}
def save(n,fig,stem,inputs,transforms):
 fig.get_layout_engine().set(rect=(0,0 if MOBILE else .13,1,.94 if MOBILE else .80))
 if MOBILE:stem+='-mobile'
 d=R/'docs/presentation';d.mkdir(parents=True,exist_ok=True);outputs=[]
 for ext in ['png','svg']:
  p=d/(stem+'.'+ext);fig.savefig(p,dpi=160,facecolor='white');outputs.append({'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 if n in ['InstrumentZero','PhotonSmith']:
  series=signal if n=='InstrumentZero' else spectrum
  gid='source-signal' if n=='InstrumentZero' else 'source-spectrum'
  xml=ET.fromstring((d/(stem+'.svg')).read_text());path=xml.find('.//s:g[@id="'+gid+'"]/s:path',{'s':'http://www.w3.org/2000/svg'})
  numbers=[float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',path.attrib['d'])]
  expected=series.get_transform().transform(series.get_xydata());scale=72/fig.dpi
  expected=[(x*scale,(fig.bbox.height-y)*scale) for x,y in expected]
  required=769 if n=='InstrumentZero' else 21
  assert len(expected)==required and len(numbers)==required*2,(n,len(numbers))
  error=max(abs(numbers[2*i+j]-point[j]) for i,point in enumerate(expected) for j in [0,1])
  assert error<0.00001,(n,error)
  manifest['source_to_svg']={'series':gid,'source_samples':required,'exported_vertices':len(numbers)//2,'maximum_svg_coordinate_error':error,'path_simplify':matplotlib.rcParams['path.simplify']}
 manifest['figures'].append({'repository':n,'inputs':[{'path':str(p.relative_to(R)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],'transformations':transforms,'outputs':outputs});plt.close(fig)
# Logical and physical circuits: gate locations/order are read directly from the saved report.
p=R/'examples/live-studio/report.json';q=json.loads(p.read_text());b=next(c for c in q['candidates'] if c['id']==q['best_id'])
fig,axs=plt.subplots(2 if MOBILE else 1,1 if MOBILE else 2,figsize=(6.4,7.4) if MOBILE else (13.2,4.4),layout='constrained');fig.suptitle('Keep the logical meaning.' if MOBILE else 'Route the circuit. Keep its meaning.',fontsize=19 if MOBILE else 23,fontweight='bold')
for ax,ops,title,prefix in [(axs[0],q['input']['operations'],'Logical input','q'),(axs[1],b['operations'],'Physical circuit on line-3','p')]:
 for y in range(3):ax.plot([.25,4],[2-y,2-y],color='#879baa',lw=1.4);ax.text(.05,2-y,prefix+str(y),ha='right',va='center',fontsize=16)
 for i,o in enumerate(ops):
  x=.8+i*1.05;ys=[2-z for z in o['qubits']]
  if o['gate']=='cx':
   ax.plot([x,x],ys,color='#145b81',lw=2);ax.add_patch(Circle((x,ys[0]),.065,color='#145b81'));ax.add_patch(Circle((x,ys[1]),.17,fill=False,edgecolor='#145b81',lw=2));ax.plot([x-.12,x+.12],[ys[1],ys[1]],color='#145b81',lw=2);ax.plot([x,x],[ys[1]-.12,ys[1]+.12],color='#145b81',lw=2)
  else:
   label={'h':'H','ry':'Ry(0.31)','u':'U'}.get(o['gate'],o['gate']);w=.82 if o['gate']=='ry' else .5;ax.add_patch(Rectangle((x-w/2,ys[0]-.23),w,.46,facecolor='#eef6fa',edgecolor='#145b81',lw=1.5,zorder=3));ax.text(x,ys[0],label,ha='center',va='center',fontsize=14,zorder=4)
 ax.set(xlim=(-.25,4.15),ylim=(-.5,2.65));ax.set_title(title,fontsize=18,loc='left',pad=13);ax.axis('off')
if not MOBILE:fig.text(.5,.065,'Logical → physical: 0 → 1, 1 → 2, 2 → 0     |     2 candidates     |     saved numerical check passed',ha='center',fontsize=13)
if not MOBILE:fig.text(.5,.025,'Recorded line-3 example; gate parameters, phase, mappings and original measurement destinations remain in the JSON/QASM.',ha='center',fontsize=10)
save('QLOOM',fig,'circuit-handoff',[p],['Gate operations and order directly rendered; no recompilation.','Logical measurement destinations omitted from circuit drawing for space; remain in source and caption.','Mapping and passed flag from selected best_id; no performance plot.'])

(R/('docs/presentation/manifest-mobile.json' if MOBILE else 'docs/presentation/manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
print('Rendered figure and manifest from exact retained source arrays.')
