from pathlib import Path
import cv2, numpy as np, json, hashlib, shutil
root=Path(__file__).resolve().parent
prior=root.parent/'35mm-delayed-processing-01'
records=[]
for i in (1,2,3):
    paths=[prior/f'{i}-{name}.png' for name in ('moderate','regional')]
    m,r=[cv2.imread(str(p),cv2.IMREAD_UNCHANGED).astype(np.float32)/65535 for p in paths]
    ml,rl=[cv2.cvtColor(x,cv2.COLOR_BGR2LAB) for x in (m,r)]
    # A warm-colour heuristic, not a face or skin identity classifier.
    a,b=ml[:,:,1],ml[:,:,2]
    warm=np.clip((b-1)/12,0,1)*np.clip((a+2)/10,0,1)
    cast=np.maximum(np.clip((a-b-5)/20,0,1),np.clip((-a-4)/15,0,1))
    weight=np.clip(0.40+0.43*warm-0.15*cast,0.25,0.83)
    weight=cv2.GaussianBlur(weight,(0,0),12)
    out=ml.copy(); out[:,:,1:]=ml[:,:,1:]*weight[:,:,None]+rl[:,:,1:]*(1-weight[:,:,None])
    combo=np.clip(cv2.cvtColor(out,cv2.COLOR_LAB2BGR),0,1)
    cv2.imwrite(str(root/f'{i}-combo.png'),np.uint16(np.rint(combo*65535)))
    cv2.imwrite(str(root/f'{i}-combo.jpg'),np.uint8(np.rint(combo*255)),[cv2.IMWRITE_JPEG_QUALITY,95])
    for old,new in [('original','original'),('monochrome','grayscale')]:
        shutil.copy2(prior/f'{i}-{old}.png',root/f'{i}-{new}.png')
    records.append({'image':i,'parents':[{ 'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],'moderate_weight_range':[float(weight.min()),float(weight.max())]})
cols=['original','grayscale','combo']
body=''
rows=[]
for i in (1,2,3):
    body+=f'<section><h2>Image {i}</h2><div class="grid">'
    thumbs=[]
    for c in cols:
        body+=f'<figure><a href="{i}-{c}.png"><img src="{i}-{c}.png" alt="Image {i}: {c}"></a><figcaption>{c}</figcaption></figure>'
        x=cv2.imread(str(root/f'{i}-{c}.png')); x=cv2.resize(x,(515,341)); cv2.putText(x,c,(12,28),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),2); thumbs.append(x)
    rows.append(np.hstack(thumbs)); body+='</div></section>'
cv2.imwrite(str(root/'comparison.jpg'),np.vstack(rows))
(root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>35mm restoration — blended colour</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}figure{margin:0}img{width:100%}figcaption{text-align:center;margin:8px}a{color:#acd}</style><h1>35mm restoration — blended colour</h1><p>Original · grayscale diagnostic · moderate/regional blend. The blend favours moderate in warm-coloured areas and regional in green/magenta areas, with smooth transitions. Colour remains an estimate. Click any image for full resolution.</p>'+body)
(root/'recipe.json').write_text(json.dumps({'opencv':cv2.__version__,'recipe':'Retain moderate Lab luminance; blend Lab chroma with regional. Moderate weight = clip(0.40 + 0.43 warm - 0.15 cast, .25,.83); Gaussian feather sigma=12 pixels. See blend.py for exact heuristic. No additional denoising or sharpening. Grayscale copied unchanged from pass 01.','records':records},indent=2))
print(root/'review.html')
