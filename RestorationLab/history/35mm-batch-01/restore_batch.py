from pathlib import Path
import sys,os,time,json,hashlib,platform,html
import setuptools  # Exposes bundled distutils for upstream thop on Python 3.12.
import cv2,numpy as np,torch
here=Path(__file__).resolve().parent
workspace=here.parent.parent
runtime=here.parent/'35mm-scunet-01'
sys.path.insert(0,str(runtime/'vendor'))
from network_scunet import SCUNet
outroot=workspace/'Restored'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic_json(path,obj):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2));os.replace(tmp,path)
def save_image(path,a,params=None):
 if path.exists():raise RuntimeError(f'Refusing overwrite: {path}')
 ok,buf=cv2.imencode(path.suffix,a,params or [])
 if not ok:raise RuntimeError(f'Encoding failed: {path}')
 tmp=path.with_name('.'+path.name+'.tmp')
 with tmp.open('xb') as f:f.write(buf.tobytes())
 check=cv2.imdecode(np.frombuffer(tmp.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
 if check is None or check.shape!=a.shape:raise RuntimeError(f'Output verification failed: {path}')
 os.link(tmp,path);tmp.unlink()
def quant16(x):return np.uint16(np.clip(x*65535,0,65535)).astype(np.float32)/65535
def colour(a):
 x=a.astype(np.float32)/255
 lo=np.percentile(x,.5,axis=(0,1));hi=np.percentile(x,99.5,axis=(0,1))
 if np.any(hi-lo<1/255):raise RuntimeError('Insufficient channel range')
 balanced=np.clip((x-lo)/(hi-lo),0,1).astype(np.float32)
 lab=cv2.cvtColor(balanced,cv2.COLOR_BGR2LAB)
 small=cv2.resize(lab[:,:,1:],(12,8),interpolation=cv2.INTER_AREA)
 results=[]
 for sigma,strength,sat in [(2,.9,1),(.6,1,.65)]:
  field=cv2.resize(cv2.GaussianBlur(small,(0,0),sigma),(a.shape[1],a.shape[0]),interpolation=cv2.INTER_CUBIC)
  work=lab.copy();work[:,:,1:]=(work[:,:,1:]-field*strength)*sat
  b=np.clip(cv2.cvtColor(work,cv2.COLOR_LAB2BGR),0,1)
  u=np.uint8(np.clip(b*255,0,255));u=cv2.fastNlMeansDenoisingColored(u,None,2,5,7,21)
  results.append(quant16(u.astype(np.float32)/255))
 ml,rl=[cv2.cvtColor(v,cv2.COLOR_BGR2LAB) for v in results]
 aa,bb=ml[:,:,1],ml[:,:,2]
 warm=np.clip((bb-1)/12,0,1)*np.clip((aa+2)/10,0,1)
 cast=np.maximum(np.clip((aa-bb-5)/20,0,1),np.clip((-aa-4)/15,0,1))
 weight=cv2.GaussianBlur(np.clip(.40+.43*warm-.15*cast,.25,.83),(0,0),12)
 work=ml.copy();work[:,:,1:]=ml[:,:,1:]*weight[:,:,None]+rl[:,:,1:]*(1-weight[:,:,None])
 result=np.clip(cv2.cvtColor(work,cv2.COLOR_LAB2BGR),0,1)
 return np.uint16(np.rint(result*65535)).astype(np.float32)/65535,lo.tolist(),hi.tolist()
def infer(bgr):
 rgb=bgr[:,:,::-1].copy();h,w=rgb.shape[:2]
 pad=np.pad(rgb,((64,128),(64,128),(0,0)),mode='reflect');result=np.empty_like(rgb)
 with torch.inference_mode():
  for y in range(0,h,256):
   for x in range(0,w,256):
    hh=min(256,h-y);ww=min(256,w-x)
    patch=pad[y:y+hh+128,x:x+ww+128]
    t=torch.from_numpy(patch.transpose(2,0,1).copy()).unsqueeze(0).to(device)
    pred=model(t).squeeze(0).permute(1,2,0).cpu().numpy()
    if not np.isfinite(pred).all():raise RuntimeError('Non-finite model output')
    result[y:y+hh,x:x+ww]=pred[64:64+hh,64:64+ww]
 return np.clip(result[:,:,::-1],0,1)
def sharpen(bgr):
 lab=cv2.cvtColor(bgr,cv2.COLOR_BGR2LAB);lum=lab[:,:,0]
 detail=lum-cv2.GaussianBlur(lum,(0,0),.8)
 lab[:,:,0]=np.clip(lum+.45*np.sign(detail)*np.maximum(np.abs(detail)-1.5,0),0,100)
 return np.clip(cv2.cvtColor(lab,cv2.COLOR_LAB2BGR),0,1)
inputs=json.loads((here/'inputs.json').read_text())
sources=[workspace/'OldScans01'/roll/(name+'.jpg') for roll,names in inputs.items() for name in names]
assert len(sources)==37 and len(set(sources))==37
for p in sources:
 if not p.is_file():raise RuntimeError(f'Missing {p}')
outroot.mkdir(exist_ok=True)
manifest_path=outroot/'restoration-manifest.json'
manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {'status':'running','recipe':'combined-colour + SCUNet real PSNR 75% blend + gentle sharpening','records':[]}
known={r['source']:r for r in manifest['records']}
# Exact pilot-source matches can reuse reviewed final output bytes.
pilots=json.loads((here.parent/'35mm-delayed-processing-01/recipe.json').read_text())['records']
pilotmap={r['sha256']:here.parent/f"35mm-scunet-sharpen-01/{r['image']}-gentle.png" for r in pilots}
torch.set_num_threads(2)
model=SCUNet(in_nc=3,config=[4]*7,dim=64)
weights=runtime/'weights/scunet_color_real_psnr.pth'
model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True),strict=True)
model.eval().requires_grad_(False)
device='mps' if torch.backends.mps.is_available() else 'cpu'
probe=torch.linspace(0,1,3*128*128).reshape(1,3,128,128)
with torch.inference_mode():
 ref=model(probe).cpu();model.to(device);actual=model(probe.to(device)).cpu()
error=(ref-actual).abs().max().item()
if not torch.isfinite(actual).all() or error>.002:device='cpu';model.to(device)
manifest.update(device=device,backend_check_max_abs=error,torch=torch.__version__,opencv=cv2.__version__,numpy=np.__version__,python=platform.python_version(),weights_sha256=digest(weights),script_sha256=digest(Path(__file__)),inputs_sha256=digest(here/'inputs.json'))
atomic_json(manifest_path,manifest)
print('Device:',device,'backend difference:',error,flush=True)
failures=[]
for index,source in enumerate(sources,1):
 start=time.monotonic();sha=digest(source);roll=source.parent.name
 directory=outroot/roll;directory.mkdir(exist_ok=True)
 png=directory/(source.stem+'.png');jpg=directory/source.name
 if str(source) in known:
  old=known[str(source)]
  if old['source_sha256']!=sha or any(digest(Path(o['path']))!=o['sha256'] for o in old['outputs']):raise RuntimeError('Resume checksum mismatch')
  print(f'{index}/37 VERIFIED {source.name}',flush=True);continue
 if png.exists() or jpg.exists():raise RuntimeError(f'Untracked output collision: {source.name}')
 print(f'{index}/37 START {source.name}',flush=True)
 try:
  a=cv2.imread(str(source),cv2.IMREAD_COLOR)
  if a is None:raise RuntimeError('JPEG decoding failed')
  reuse=pilotmap.get(sha)
  lo=hi=None
  if reuse:
   final=cv2.imread(str(reuse),cv2.IMREAD_UNCHANGED).astype(np.float32)/65535
   reused=str(reuse)
  else:
   combo,lo,hi=colour(a)
   ai=infer(combo)
   # Reproduce the pilot's stored uint16 blend before sharpening.
   blend=np.uint16(np.rint((.75*ai+.25*combo)*65535)).astype(np.float32)/65535
   final=sharpen(blend);reused=None
  if final.shape!=a.shape or not np.isfinite(final).all():raise RuntimeError('Invalid result')
  if digest(source)!=sha:raise RuntimeError('Source changed during processing')
  save_image(png,np.uint16(np.rint(final*65535)))
  save_image(jpg,np.uint8(np.rint(final*255)),[cv2.IMWRITE_JPEG_QUALITY,95])
  record={'source':str(source),'source_sha256':sha,'shape':list(a.shape),'seconds':time.monotonic()-start,'percentiles_bgr':[lo,hi],'reused_reviewed_output':reused,'outputs':[{'path':str(p),'sha256':digest(p)} for p in (png,jpg)]}
  manifest['records'].append(record);atomic_json(manifest_path,manifest)
  print(f'{index}/37 DONE {source.name} {record["seconds"]:.1f}s',flush=True)
 except Exception as e:
  failures.append({'source':str(source),'error':str(e)});manifest['failures']=failures;atomic_json(manifest_path,manifest)
  print(f'{index}/37 FAILED {source.name}: {e}',flush=True)
# Verify every source and output after processing, and report all omissions.
for r in manifest['records']:
 if digest(Path(r['source']))!=r['source_sha256']:raise RuntimeError('Source changed')
 for o in r['outputs']:
  if digest(Path(o['path']))!=o['sha256']:raise RuntimeError('Output changed')
manifest['status']='complete' if len(manifest['records'])==37 and not failures else 'incomplete'
manifest['failures']=failures;atomic_json(manifest_path,manifest)
body=''
for r in manifest['records']:
 p=Path(r['source']); rel=Path('..')/p.relative_to(workspace);dest=Path(p.parent.name)/p.name;png=dest.with_suffix('.png')
 body+=f'<section><h2>{html.escape(p.name)}</h2><div class="pair"><figure><a href="{rel}"><img loading="lazy" src="{rel}"></a><figcaption>Original</figcaption></figure><figure><a href="{png}"><img loading="lazy" src="{dest}"></a><figcaption>Restored · <a href="{dest}">JPEG</a> · <a href="{png}">PNG</a></figcaption></figure></div></section>'
(outroot/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Restored film scans</title><style>body{background:#202124;color:#eee;font:16px system-ui;margin:24px}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}img{width:100%}figure{margin:0}figcaption{text-align:center;margin:8px}a{color:#acd}section{margin-bottom:36px}</style><h1>Restored film scans</h1><p>'+str(len(manifest['records']))+' / 37 restored. Combined colour correction → 75% SCUNet blend → gentle sharpening. Original orientation retained; no cropping or upscaling. All processing local. Colour correction uses the selected experimental recipe and may affect genuine colours. PNG masters and quality-95 JPEGs; 16-bit storage adds no recovered source precision.</p>'+body)
print('BATCH',manifest['status'],len(manifest['records']),'of 37',flush=True)
if failures:sys.exit(1)
