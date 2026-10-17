from pathlib import Path
import sys,time,json,hashlib,platform
import torch,cv2,numpy as np
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'vendor'))
from network_scunet import SCUNet
weights=root/'weights/scunet_color_real_psnr.pth'
torch.set_num_threads(2)
model=SCUNet(in_nc=3,config=[4,4,4,4,4,4,4],dim=64)
model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True),strict=True)
model.eval().requires_grad_(False)
device='mps' if torch.backends.mps.is_available() else 'cpu'
print('Device:',device,flush=True)
# Verify backend on real image data before the batch.
probe=cv2.imread(str(root.parent/'35mm-delayed-processing-02/3-combo.png'),cv2.IMREAD_UNCHANGED).astype(np.float32)/65535
probe=torch.from_numpy(probe[256:384,896:1024,::-1].copy().transpose(2,0,1)).unsqueeze(0)
with torch.inference_mode():
    ref=model(probe).cpu()
    model.to(device); test=model(probe.to(device)).cpu()
    error=(ref-test).abs().max().item()
print('CPU/device max difference:',error,flush=True)
if not torch.isfinite(test).all() or error>.002: device='cpu';model.to(device);print('Using CPU after verification failure',flush=True)
records=[]
for i in [3,1,2]:
    source=root.parent/f'35mm-delayed-processing-02/{i}-combo.png'
    output=root/f'{i}-scunet.png'
    if output.exists(): print('Cached',i,flush=True);continue
    bgr=cv2.imread(str(source),cv2.IMREAD_UNCHANGED).astype(np.float32)/65535
    rgb=bgr[:,:,::-1].copy();h,w=rgb.shape[:2]
    # Core tiles with 64-pixel context, keeping inference grid aligned to 64.
    pad=np.pad(rgb,((64,128),(64,128),(0,0)),mode='reflect')
    result=np.empty_like(rgb);start=time.monotonic()
    with torch.inference_mode():
        for y in range(0,h,256):
            for x in range(0,w,256):
                hh=min(256,h-y);ww=min(256,w-x)
                patch=pad[y:y+hh+128,x:x+ww+128]
                t=torch.from_numpy(patch.transpose(2,0,1).copy()).unsqueeze(0).to(device)
                pred=model(t).squeeze(0).permute(1,2,0).cpu().numpy()
                if not np.isfinite(pred).all():raise RuntimeError('Non-finite output')
                result[y:y+hh,x:x+ww]=pred[64:64+hh,64:64+ww]
            print(f'Image {i}: {min(y+256,h)}/{h} rows',flush=True)
    out=np.clip(result[:,:,::-1],0,1)
    cv2.imwrite(str(output),np.uint16(np.rint(out*65535)))
    blend=.75*out+.25*bgr
    cv2.imwrite(str(root/f'{i}-blend75.png'),np.uint16(np.rint(blend*65535)))
    records.append({'image':i,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'seconds':time.monotonic()-start})
    (root/'run.json').write_text(json.dumps({'device':device,'backend_check_max_abs':error,'torch':torch.__version__,'python':platform.python_version(),'weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),'tile_core':256,'halo':64,'model':'scunet_color_real_psnr','no_additional_sharpening':True,'records':records},indent=2))
print('Complete',flush=True)
