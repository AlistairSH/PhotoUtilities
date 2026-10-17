from pathlib import Path
import cv2,numpy as np,json,hashlib,shutil
root=Path(__file__).resolve().parent
prior=root.parent/'35mm-delayed-processing-05'
regions={1:[(830,170,400,350),(500,460,400,350)],2:[(880,160,400,350),(440,460,400,350)],3:[(880,260,400,350),(370,210,400,350)]}
records=[];body='';sheets=[]
for i in (1,2,3):
    source=prior/f'{i}-candidate.png'; raw=cv2.imread(str(source),cv2.IMREAD_UNCHANGED)
    baseline=raw.astype(np.float32)/65535
    lab=cv2.cvtColor(baseline,cv2.COLOR_BGR2LAB)
    # Estimate broad colour variation at low resolution; suppress only green/magenta excess.
    broad=cv2.resize(cv2.GaussianBlur(cv2.resize(lab[:,:,1:],(24,16),interpolation=cv2.INTER_AREA),(0,0),1.2),(raw.shape[1],raw.shape[0]),interpolation=cv2.INTER_CUBIC)
    aa,bb=broad[:,:,0],broad[:,:,1]
    green=np.clip((-aa-3)/12,0,1)
    magenta=np.clip((aa-bb-5)/16,0,1)*np.clip((aa-2)/10,0,1)
    mask=cv2.GaussianBlur(np.maximum(green,magenta),(0,0),18)
    corrected=lab.copy()
    corrected[:,:,1:]-=0.40*mask[:,:,None]*broad
    color=np.clip(cv2.cvtColor(corrected,cv2.COLOR_LAB2BGR),0,1)
    # Additional denoising targets dark, low-structure regions; edges are protected.
    u=np.uint8(np.rint(color*255))
    smooth=cv2.fastNlMeansDenoisingColored(u,None,15,18,7,21).astype(np.float32)/255
    lum=corrected[:,:,0]; guide=cv2.GaussianBlur(lum,(0,0),2)
    gx=cv2.Sobel(guide,cv2.CV_32F,1,0,ksize=3)/8
    gy=cv2.Sobel(guide,cv2.CV_32F,0,1,ksize=3)/8
    edge=cv2.GaussianBlur(np.sqrt(gx*gx+gy*gy),(0,0),2)
    shadow=np.clip((48-guide)/30,0,1)
    weight=cv2.GaussianBlur(.65*shadow*np.clip(1-edge/3,0,1),(0,0),3)
    cleaned=np.clip(color*(1-weight[:,:,None])+smooth*weight[:,:,None],0,1)
    variants={'midpoint':baseline,'cleanup':cleaned}
    shutil.copy2(source,root/f'{i}-midpoint.png')
    cv2.imwrite(str(root/f'{i}-cleanup.png'),np.uint16(np.rint(cleaned*65535)))
    cv2.imwrite(str(root/f'{i}-cleanup.jpg'),np.uint8(np.rint(cleaned*255)),[cv2.IMWRITE_JPEG_QUALITY,95])
    cv2.imwrite(str(root/f'{i}-colour-mask.png'),np.uint8(np.rint(mask*255)))
    cv2.imwrite(str(root/f'{i}-shadow-mask.png'),np.uint8(np.rint(weight*255)))
    body+=f'<section><h2>Image {i}</h2><div class="grid">';thumbs=[]
    for name,out in variants.items():
        body+=f'<figure><a href="{i}-{name}.png"><img src="{i}-{name}.png"></a><figcaption>{name}</figcaption></figure>'
        thumb=cv2.resize(np.uint8(np.rint(out*255)),(618,410));cv2.putText(thumb,name,(12,28),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2);thumbs.append(thumb)
    sheets.append(np.hstack(thumbs));body+='</div><details open><summary>100% detail crops</summary>'
    for j,(x,y,w,h) in enumerate(regions[i],1):
        body+=f'<h3>Detail {j}</h3><div class="crops">'
        for name,out in variants.items():
            dest=f'{i}-{name}-crop{j}.png';cv2.imwrite(str(root/dest),np.uint8(np.rint(out[y:y+h,x:x+w]*255)))
            body+=f'<figure><img src="{dest}" width="400" height="350"><figcaption>{name}</figcaption></figure>'
        body+='</div>'
    body+='</details></section>'
    records.append({'image':i,'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'colour_mask_mean':float(mask.mean()),'shadow_blend_mean':float(weight.mean()),'crops_xywh':regions[i]})
cv2.imwrite(str(root/'comparison.jpg'),np.vstack(sheets))
(root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>35mm selective cleanup</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid img{width:100%}.crops{display:flex;gap:16px;overflow-x:auto}.crops img{max-width:none}figure{margin:0}figcaption{text-align:center;margin:8px}summary{cursor:pointer;margin:20px 0}section{margin-bottom:44px}</style><h1>Selective colour and shadow cleanup</h1><p>Midpoint candidate → selective cleanup. Broad green/magenta colour excess is reduced with feathered masks. Additional noise reduction is blended into dark, low-structure areas with edge protection. These are colour heuristics, not calibrated film recovery; genuine colours can also be affected. No additional sharpening or reconstruction.</p><p>Click full images for full-resolution PNGs. Crops display at native pixel dimensions.</p>'+body)
(root/'recipe.json').write_text(json.dumps({'opencv':cv2.__version__,'colour':'24x16 Lab chroma field, sigma=1.2 grid units; green/magenta excess heuristic; mask feather sigma=18 px; subtract 40% masked broad chroma','shadow':'NLM h=15 hColor=18 template=7 search=21; blend max .65 in dark low-structure areas; exact masks in cleanup.py','records':records},indent=2))
print(root/'review.html')
