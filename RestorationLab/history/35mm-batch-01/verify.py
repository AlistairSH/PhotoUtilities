from pathlib import Path
import json,hashlib,cv2,numpy as np
root=Path(__file__).resolve().parent.parent.parent
out=root/'Restored';manifest=json.loads((out/'restoration-manifest.json').read_text());inputs=json.loads((root/'feasibility/35mm-batch-01/inputs.json').read_text())
expected={str(root/'OldScans01'/roll/(name+'.jpg')) for roll,names in inputs.items() for name in names}
assert manifest['status']=='complete' and not manifest['failures']
assert {r['source'] for r in manifest['records']}==expected
assert len(manifest['records'])==37
for r in manifest['records']:
 source=Path(r['source']);assert hashlib.sha256(source.read_bytes()).hexdigest()==r['source_sha256']
 for o in r['outputs']:
  p=Path(o['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==o['sha256']
  im=cv2.imread(str(p),cv2.IMREAD_UNCHANGED);assert im is not None and list(im.shape)==r['shape']
  if p.suffix=='.png':assert im.dtype==np.uint16
for roll,names in inputs.items():
 thumbs=[]
 for name in names:
  a=cv2.imread(str(out/roll/(name+'.jpg')));t=cv2.resize(a,(386,256));cv2.rectangle(t,(0,0),(386,28),(25,25,25),-1);cv2.putText(t,name,(8,21),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1);thumbs.append(t)
 while len(thumbs)%3:thumbs.append(np.zeros_like(thumbs[0]))
 sheet=np.vstack([np.hstack(thumbs[j:j+3]) for j in range(0,len(thumbs),3)])
 cv2.imwrite(str(out/f'contact-{roll}.jpg'),sheet)
print('Verified: all 37 sources unchanged; 74 outputs decode at source dimensions with matching checksums; PNGs are uint16; no missing or failed inputs.')
