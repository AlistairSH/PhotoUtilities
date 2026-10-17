from pathlib import Path
import cv2,numpy as np,json,hashlib,shutil
root=Path(__file__).resolve().parent
prior=root.parent/'35mm-delayed-processing-02'
records=[];body=''
regions={1:(830,170,400,350),2:(880,160,400,350),3:(880,260,400,350)}
for i in (1,2,3):
    source=prior/f'{i}-combo.png'; a=cv2.imread(str(source),cv2.IMREAD_UNCHANGED)
    u=np.uint8(np.rint(a.astype(np.float32)/257))
    den=cv2.fastNlMeansDenoisingColored(u,None,10.5,14,7,21)
    lab=cv2.cvtColor(den.astype(np.float32)/255,cv2.COLOR_BGR2LAB)
    lum=lab[:,:,0];detail=lum-cv2.GaussianBlur(lum,(0,0),.95)
    lab[:,:,0]=np.clip(lum+.625*np.sign(detail)*np.maximum(np.abs(detail)-1.75,0),0,100)
    out=np.clip(cv2.cvtColor(lab,cv2.COLOR_LAB2BGR),0,1)
    cv2.imwrite(str(root/f'{i}-candidate.png'),np.uint16(np.rint(out*65535)))
    cv2.imwrite(str(root/f'{i}-candidate.jpg'),np.uint8(np.rint(out*255)),[cv2.IMWRITE_JPEG_QUALITY,95])
    cv2.imwrite(str(root/f'{i}-denoised.png'),den)
    for c in ('original','grayscale'):shutil.copy2(prior/f'{i}-{c}.png',root/f'{i}-{c}.png')
    x,y,w,h=regions[i];cv2.imwrite(str(root/f'{i}-detail.png'),np.uint8(np.rint(out[y:y+h,x:x+w]*255)))
    body+=f'<h2>Image {i}</h2><div class="grid">'+''.join(f'<figure><a href="{i}-{c}.png"><img src="{i}-{c}.png"></a><figcaption>{c}</figcaption></figure>' for c in ('original','grayscale','candidate'))+f'</div><details><summary>Candidate face detail, 100%</summary><img src="{i}-detail.png" width="400" height="350"></details>'
    records.append({'image':i,'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'face_crop_xywh':regions[i]})
(root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>35mm midpoint candidate</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.grid img{width:100%}figure{margin:0}figcaption{text-align:center;margin:8px}summary{cursor:pointer;margin:20px 0}</style><h1>35mm midpoint candidate</h1><p>Original → grayscale diagnostic → combined colour with midpoint denoising and sharpening. Click for full resolution. Denoising: h=10.5, colour=14. Sharpening: sigma=.95 px, amount=.625, soft threshold=1.75 Lab L units. All local, no reconstruction. Source remains 8-bit JPEG; 16-bit output storage adds no recovered precision.</p>'+body)
(root/'recipe.json').write_text(json.dumps({'opencv':cv2.__version__,'denoise':{'h':10.5,'hColor':14,'templateWindowSize':7,'searchWindowSize':21},'sharpen':{'method':'Lab luminance soft-threshold unsharp mask','sigma':.95,'amount':.625,'threshold':1.75},'records':records},indent=2))
print(root/'review.html')
