from pathlib import Path
import cv2,numpy as np,json
root=Path(__file__).resolve().parent
regions={1:[(830,170,400,350),(500,460,400,350)],2:[(880,160,400,350),(440,460,400,350)],3:[(880,260,400,350),(370,210,400,350)]}
body='';sheet=[]
for i in (1,2,3):
    paths={'Colour input':root.parent/f'35mm-delayed-processing-02/{i}-combo.png','Current conventional':root.parent/f'35mm-delayed-processing-06/{i}-cleanup.png','SCUNet':root/f'{i}-scunet.png','75% SCUNet blend':root/f'{i}-blend75.png'}
    body+=f'<h2>Image {i}</h2><div class="grid">';images={};thumbs=[]
    for j,(label,path) in enumerate(paths.items()):
        raw=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
        if raw is None:raise RuntimeError(f'Missing {path}')
        u=np.uint8(np.rint(raw.astype(np.float32)/257)) if raw.dtype==np.uint16 else raw
        images[label]=u; preview=f'{i}-view{j}.jpg';cv2.imwrite(str(root/preview),u,[cv2.IMWRITE_JPEG_QUALITY,95])
        rel=Path('../')/path.relative_to(root.parent)
        body+=f'<figure><a href="{rel}"><img src="{preview}"></a><figcaption>{label}</figcaption></figure>'
        t=cv2.resize(u,(386,256));cv2.putText(t,label,(8,23),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1);thumbs.append(t)
    sheet.append(np.hstack(thumbs));body+='</div><details open><summary>100% detail crops</summary>'
    for k,(x,y,w,h) in enumerate(regions[i]):
        body+='<div class="crops">'
        for j,(label,u) in enumerate(images.items()):
            name=f'{i}-crop{k}-{j}.png';cv2.imwrite(str(root/name),u[y:y+h,x:x+w]);body+=f'<figure><img src="{name}" width="400" height="350"><figcaption>{label}</figcaption></figure>'
        body+='</div>'
    body+='</details>'
cv2.imwrite(str(root/'comparison.jpg'),np.vstack(sheet))
run=json.loads((root/'run.json').read_text())
(root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>SCUNet local feasibility</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.grid img{width:100%}figure{margin:0}figcaption{text-align:center;margin:8px}.crops{display:flex;gap:12px;overflow-x:auto;margin:20px 0}.crops img{max-width:none}summary{cursor:pointer;margin:20px 0}</style><h1>SCUNet local feasibility</h1><p>AI input is the combined colour version before conventional denoising/sharpening. Current conventional includes midpoint denoising, sharpening and selective cleanup. SCUNet and its 75% blend have no added sharpening or upscaling. The blend is 75% model output + 25% colour input. This comparison evaluates complete alternatives; it does not isolate sharpening.</p><p>Model: scunet_color_real_psnr. Device: '+run['device']+'. 256px core tiles with 64px context. All inference local. Click full images for full resolution. Crops use native pixel dimensions.</p>'+body)
print(root/'review.html')
