"""Compare local scalar edge intermediates with the accepted OpenCV implementation."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from photo_utils.focus_edges import extract,summarize


def run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('fixture',type=Path);p.add_argument('trace',type=Path)
    p.add_argument('--index',type=int,default=19);p.add_argument('--scale',type=int,default=2048)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    views=json.loads((a.fixture/'views.json').read_text())
    view=next(r for r in views if r['index']==a.index and r['max_dimension']==a.scale)
    w,h=view['width'],view['height'];name=f'{a.index:04d}-{a.scale}.rgba'
    data=(a.fixture/'pixels'/name).read_bytes()
    manifest=json.loads((a.fixture/'complete.json').read_text())
    assert hashlib.sha256(data).hexdigest()==manifest['pixels_sha256'][name]
    rgba=np.frombuffer(data,np.uint8).reshape(h,w,4)
    gray=cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2GRAY)
    image=cv2.GaussianBlur(gray.astype(np.float32)/255,(0,0),1.)
    dx=cv2.Sobel(image,cv2.CV_32F,1,0,ksize=3);dy=cv2.Sobel(image,cv2.CV_32F,0,1,ksize=3)
    magnitude=cv2.magnitude(dx,dy)
    output={'index':a.index,'scale':a.scale,'intermediates':{}}
    for name,baseline in [('input',gray.astype(np.float32)/255),('gaussian',image),('dx',dx),('dy',dy),('magnitude',magnitude)]:
        path=a.trace/(name+'.f32')
        if not path.exists():continue
        native=np.fromfile(path,dtype=np.float32).reshape(h,w)
        output['intermediates'][name]={'unequal_pixels':int(np.sum(baseline!=native)),'max_absolute_error':float(np.max(np.abs(baseline-native)))}
    def selection(magnitude):
        y,x=np.mgrid[18:h-18:3,18:w-18:3];x=x.ravel();y=y.ravel();m=magnitude[y,x]
        threshold=max(.002,float(np.quantile(m,.75)));choose=m>threshold;x=x[choose];y=y[choose]
        count=len(x)
        if count>3000:
            take=np.random.default_rng(0).choice(count,3000,replace=False);x=x[take];y=y[take]
        return count,threshold,list(zip(x.tolist(),y.tolist()))
    count,threshold,selected=selection(magnitude)
    native_x=np.fromfile(a.trace/'selected_x.f32',dtype=np.float32).astype(int)
    native_y=np.fromfile(a.trace/'selected_y.f32',dtype=np.float32).astype(int)
    native_selected=list(zip(native_x.tolist(),native_y.tolist()))
    nc,nt,_=selection(np.fromfile(a.trace/'magnitude.f32',dtype=np.float32).reshape(h,w))
    output['selection']={'baseline_candidates':count,'native_candidates':nc,'baseline_threshold':threshold,'native_threshold':nt,
        'selected_set_intersection':len(set(selected)&set(native_selected)),'selected_count':len(selected),'selection_order_equal':selected==native_selected}
    baseline=extract(gray);native=json.loads((a.trace/'profiles.json').read_text())
    output['global_counts']={'baseline':len(baseline['width']),'native':len(native['width'])}
    output['regions']=[]
    for kind in ('faces','people','animals','objectness','attention'):
        for i,region in enumerate(view['detectors'][kind]['regions']):
            box=region.get('display_box',region['box'])
            b=summarize(baseline,box,(h,w));n=summarize(native,box,(h,w))
            output['regions'].append({'id':f'{kind} {i+1}','baseline':b,'native':n})
    with a.output.open('x') as file:json.dump(output,file,indent=2)
    print(json.dumps({k:v for k,v in output.items() if k!='regions'},indent=2))

if __name__=='__main__':run()
