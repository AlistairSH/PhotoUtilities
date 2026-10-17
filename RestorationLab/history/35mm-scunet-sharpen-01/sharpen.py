from pathlib import Path
import cv2,numpy as np,json,hashlib,shutil
root=Path(__file__).resolve().parent
prior=root.parent/'35mm-scunet-01'
settings={'very-gentle':(.65,.25,1.0),'gentle':(.8,.45,1.5)}
regions={1:[(830,170,400,350),(500,460,400,350)],2:[(880,160,400,350),(440,460,400,350)],3:[(880,260,400,350),(370,210,400,350)]}
records=[];body='';sheets=[]
for i in (1,2,3):
    source=prior/f'{i}-blend75.png';raw=cv2.imread(str(source),cv2.IMREAD_UNCHANGED)
    x=raw.astype(np.float32)/65535;lab=cv2.cvtColor(x,cv2.COLOR_BGR2LAB)
    variants={'unsharpened':x}
    for name,(sigma,amount,threshold) in settings.items():
        lum=lab[:,:,0];detail=lum-cv2.GaussianBlur(lum,(0,0),sigma)
        out=lab.copy();out[:,:,0]=np.clip(lum+amount*np.sign(detail)*np.maximum(np.abs(detail)-threshold,0),0,100)
        variants[name]=np.clip(cv2.cvtColor(out,cv2.COLOR_LAB2BGR),0,1)
    body+=f'<section><h2>Image {i}</h2><div class="grid">';thumbs=[]
    for name,out in variants.items():
        stem=f'{i}-{name}'
        if name=='unsharpened':shutil.copy2(source,root/f'{stem}.png')
        else:cv2.imwrite(str(root/f'{stem}.png'),np.uint16(np.rint(out*65535)))
        u=np.uint8(np.rint(out*255));cv2.imwrite(str(root/f'{stem}.jpg'),u,[cv2.IMWRITE_JPEG_QUALITY,95])
        body+=f'<figure><a href="{stem}.png"><img src="{stem}.jpg"></a><figcaption>{name}</figcaption></figure>'
        thumb=cv2.resize(u,(515,341));cv2.putText(thumb,name,(12,27),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),2);thumbs.append(thumb)
    sheets.append(np.hstack(thumbs));body+='</div><details open><summary>100% detail crops</summary>'
    for j,(cx,cy,w,h) in enumerate(regions[i],1):
        body+=f'<h3>Detail {j}</h3><div class="crops">'
        for name,out in variants.items():
            dest=f'{i}-{name}-crop{j}.png';cv2.imwrite(str(root/dest),np.uint8(np.rint(out[cy:cy+h,cx:cx+w]*255)))
            body+=f'<figure><img src="{dest}" width="400" height="350"><figcaption>{name}</figcaption></figure>'
        body+='</div>'
    body+='</details></section>'
    records.append({'image':i,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'crop_xywh':regions[i]})
cv2.imwrite(str(root/'comparison.jpg'),np.vstack(sheets))
(root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>SCUNet blend sharpening</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.grid img{width:100%}.crops{display:flex;gap:12px;overflow-x:auto}.crops img{max-width:none}figure{margin:0}figcaption{text-align:center;margin:8px}summary{cursor:pointer;margin:20px 0}section{margin-bottom:48px}</style><h1>Sharpening the 75% SCUNet blend</h1><p>Unsharpened → very gentle → gentle. Luminance-only soft-threshold unsharp masking, with no added denoising, colour correction, upscaling or model inference. Click full images for full-resolution PNGs. Detail crops display at native pixel dimensions.</p><p>Very gentle: sigma=0.65 px, amount=0.25, threshold=1.0 Lab L units. Gentle: sigma=0.8 px, amount=0.45, threshold=1.5. The gentle recipe matches the earlier conventional sharpening test.</p>'+body)
(root/'recipe.json').write_text(json.dumps({'opencv':cv2.__version__,'method':'Lab luminance soft-threshold unsharp mask','settings_sigma_amount_threshold':settings,'processing_depth':'float32; 16-bit PNG storage; sRGB assumed as in prior passes','records':records},indent=2))
print(root/'review.html')
