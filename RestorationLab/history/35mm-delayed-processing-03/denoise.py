from pathlib import Path
import cv2,numpy as np,json,hashlib,shutil
root=Path(__file__).resolve().parent
prior=root.parent/'35mm-delayed-processing-02'
settings={'light':(4,9),'balanced':(8,12),'strong':(13,16)}
records=[]
# Fixed inspection regions, in source pixels: face and bedding/skin texture.
regions={1:[(830,170,400,350),(500,460,400,350)],2:[(880,160,400,350),(440,460,400,350)],3:[(880,260,400,350),(370,210,400,350)]}
cols=['baseline',*settings]
body=''; contact=[]
for i in (1,2,3):
    source=prior/f'{i}-combo.png'
    a=cv2.imread(str(source),cv2.IMREAD_UNCHANGED)
    u=np.uint8(np.rint(a.astype(np.float32)/257))
    shutil.copy2(source,root/f'{i}-baseline.png')
    variants={'baseline':u}
    for name,(h,hc) in settings.items():
        out=cv2.fastNlMeansDenoisingColored(u,None,h,hc,7,21)
        variants[name]=out
        cv2.imwrite(str(root/f'{i}-{name}.png'),out.astype(np.uint16)*257)
        cv2.imwrite(str(root/f'{i}-{name}.jpg'),out,[cv2.IMWRITE_JPEG_QUALITY,95])
    body+=f'<section><h2>Image {i}</h2><div class="grid">'
    thumbs=[]
    for name,out in variants.items():
        body+=f'<figure><a href="{i}-{name}.png"><img src="{i}-{name}.png"></a><figcaption>{name}</figcaption></figure>'
        thumb=cv2.resize(out,(386,256));cv2.putText(thumb,name,(10,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2);thumbs.append(thumb)
    contact.append(np.hstack(thumbs));body+='</div><details open><summary>100% detail crops</summary>'
    for j,(x,y,w,h) in enumerate(regions[i],1):
        body+=f'<h3>Detail {j}</h3><div class="crops">'
        for name,out in variants.items():
            dest=f'{i}-{name}-crop{j}.png';cv2.imwrite(str(root/dest),out[y:y+h,x:x+w])
            body+=f'<figure><img src="{dest}" width="400" height="350"><figcaption>{name}</figcaption></figure>'
        body+='</div>'
    body+='</details></section>'
    records.append({'image':i,'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'crops_xywh':regions[i]})
cv2.imwrite(str(root/'comparison.jpg'),np.vstack(contact))
(root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>35mm denoising comparison</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.grid img{width:100%}.crops{display:flex;gap:12px;overflow-x:auto}.crops img{max-width:none}figure{margin:0}figcaption{text-align:center;margin:8px}summary{cursor:pointer;margin:20px 0}section{margin-bottom:40px}</style><h1>Local denoising feasibility</h1><p>Baseline combined colour, then light, balanced and strong OpenCV non-local means. No sharpening or additional colour adjustment. Crops display at native pixel dimensions; scroll horizontally if necessary. Click full images for full resolution.</p><p>Light: h=4 / colour=9. Balanced: h=8 / colour=12. Strong: h=13 / colour=16. All use template=7, search=21. Processing uses 8-bit values; 16-bit PNG storage adds no source precision.</p>'+body)
(root/'recipe.json').write_text(json.dumps({'opencv':cv2.__version__,'method':'fastNlMeansDenoisingColored','settings_h_hColor':settings,'templateWindowSize':7,'searchWindowSize':21,'processing_depth':8,'sharpening':False,'records':records},indent=2))
print(root/'review.html')
