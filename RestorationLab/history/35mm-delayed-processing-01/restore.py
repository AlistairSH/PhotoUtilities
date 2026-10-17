from pathlib import Path
import cv2, numpy as np, hashlib, json, html
root=Path(__file__).resolve().parent
sources=[Path('/var/folders/s0/3dlt7db95ylfvcq6c2_9j6hw0000gn/T')/n for n in ['codex-clipboard-2c6af0b2-97af-4490-ac52-420c7a052a8f.jpg','codex-clipboard-f60ef1f0-d341-4693-b735-f800b8819324.jpg','codex-clipboard-c28129ed-9d22-44cd-8fa7-6a8791d64d56.jpg']]
records=[]
for i,p in enumerate(sources,1):
    raw=p.read_bytes(); a=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR); x=a.astype(np.float32)/255
    cv2.imwrite(str(root/f'{i}-original.png'),a)
    lo=np.percentile(x,0.5,axis=(0,1)); hi=np.percentile(x,99.5,axis=(0,1))
    balanced=np.clip((x-lo)/(hi-lo),0,1).astype(np.float32)
    # Gray-world spatial correction is an explicit hypothesis, not measured film calibration.
    lab=cv2.cvtColor(balanced,cv2.COLOR_BGR2LAB)
    small=cv2.resize(lab[:,:,1:],(12,8),interpolation=cv2.INTER_AREA)
    field=cv2.resize(cv2.GaussianBlur(small,(0,0),2),(a.shape[1],a.shape[0]),interpolation=cv2.INTER_CUBIC)
    variants={'global':balanced}
    for name,strength in [('conservative',0.55),('moderate',0.9),('regional',1.0)]:
        work=lab.copy()
        correction=field
        if name=='regional':
            correction=cv2.resize(cv2.GaussianBlur(small,(0,0),0.6),(a.shape[1],a.shape[0]),interpolation=cv2.INTER_CUBIC)
        work[:,:,1:]-=correction*strength
        if name=='regional': work[:,:,1:]*=0.65
        b=np.clip(cv2.cvtColor(work,cv2.COLOR_LAB2BGR),0,1)
        # Gentle chroma denoise; luminance retained to avoid erasing facial detail.
        u=np.uint8(np.clip(b*255,0,255)); u=cv2.fastNlMeansDenoisingColored(u,None,2,5,7,21)
        variants[name]=u.astype(np.float32)/255
    gray=cv2.cvtColor(balanced,cv2.COLOR_BGR2GRAY)
    variants['monochrome']=np.repeat(gray[:,:,None],3,axis=2)
    for name,b in variants.items():
        cv2.imwrite(str(root/f'{i}-{name}.png'),np.uint16(np.clip(b*65535,0,65535)))
        cv2.imwrite(str(root/f'{i}-{name}.jpg'),np.uint8(np.clip(b*255,0,255)),[cv2.IMWRITE_JPEG_QUALITY,95])
    records.append(dict(image=i,source=str(p),sha256=hashlib.sha256(raw).hexdigest(),shape=list(a.shape),percentiles_bgr=[lo.tolist(),hi.tolist()],source_profile='No profile conversion; decoded JPEG values treated as sRGB for this feasibility pass'))
(root/'recipe.json').write_text(json.dumps(dict(opencv=cv2.__version__,numpy=np.__version__,records=records,recipe='0.5/99.5 per-channel stretch; Lab broad chroma field from 12x8 grid blurred sigma=2; subtract 55% or 90%; NLM luminance=2 colour=5; no sharpening, inference or reconstruction'),indent=2))
cols=['original','global','conservative','moderate','regional','monochrome']
body=''.join('<section><h2>Image '+str(i)+'</h2><div class="grid">'+''.join(f'<figure><a href="{i}-{c}.png"><img src="{i}-{c}.png"></a><figcaption>{c}</figcaption></figure>' for c in cols)+'</div></section>' for i in [3,1,2])
(root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Delayed-processing 35mm feasibility</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0}img{width:100%}figcaption{text-align:center}a{color:#acd}</style><h1>35mm scan restoration — local feasibility</h1><p>Colour correction hypotheses, not calibrated original colours. Click an image for full resolution. Originals preserved. PNG derivatives are 16-bit; the source remains 8-bit JPEG.</p>'+body)
# Pilot contact sheet for visual inspection.
thumbs=[]
for c in cols:
    b=cv2.imread(str(root/f'3-{c}.png')); b=cv2.resize(b,(618,410)); cv2.putText(b,c,(15,30),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2); thumbs.append(b)
cv2.imwrite(str(root/'pilot-comparison.jpg'),np.vstack([np.hstack(thumbs[:3]),np.hstack([thumbs[3],thumbs[4],thumbs[5]])]))
print(root/'review.html')
