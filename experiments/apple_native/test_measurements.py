"""Synthetic pixel tests against accepted OpenCV/NumPy measurements."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from photo_utils.focus import measure
from photo_utils.tiers import exposure
from freeze_evidence import digest


def run(binary):
    with tempfile.TemporaryDirectory(prefix='apple-native-numeric-',dir='/private/tmp') as temp:
        root=Path(temp);(root/'pixels').mkdir()
        views=[];baseline=[];hashes={}
        h,w=128,128
        step=np.zeros((h,w),np.uint8);step[:,w//2:]=255
        rng=np.random.default_rng(8)
        images=[np.full((h,w,3),128,np.uint8),np.repeat(step[:,:,None],3,axis=2),
                np.repeat(cv2.GaussianBlur(step,(0,0),3.)[:,:,None],3,axis=2),rng.integers(0,256,(h,w,3),dtype=np.uint8)]
        for index,rgb in enumerate(images):
            detectors={kind:{'status':'ok','regions':[]} for kind in ('faces','people','animals','objectness','attention')}
            detectors['faces']['regions']=[{'box':[0,0,.5,.5]}]
            detectors['animals']['regions']=[{'box':[.5,.5,.5,.5]}]
            detectors['objectness']['regions']=[{'box':[-.1,.2,.4,.7]}]
            detectors['attention']['regions']=[{'box':[.1234,.2345,.4567,.3456]}]
            pixels=np.dstack((rgb,np.full((h,w),255,np.uint8))).tobytes()
            name=f'{index:04d}-1024.rgba';path=root/'pixels'/name;path.write_bytes(pixels);hashes[name]=digest(path)
            views.append({'index':index,'path':f'synthetic-{index}','max_dimension':1024,'width':w,'height':h,'detectors':copy.deepcopy(detectors)})
            row=measure(rgb,copy.deepcopy(detectors),f'synthetic-{index}',1024)
            row['exposure']=exposure(rgb,detectors);baseline.append(row)
        (root/'views.json').write_text(json.dumps(views))
        (root/'complete.json').write_text(json.dumps({'pixels_sha256':hashes,'files':{'views.json':digest(root/'views.json')}}))
        completed=subprocess.run([binary,str(root),str(root/'measured.jsonl')],capture_output=True,text=True,timeout=120)
        if completed.returncode:raise AssertionError(completed.stderr)
        rows=[json.loads(line) for line in (root/'measured.jsonl').read_text().splitlines()][:-1]
        for i,(a,b) in enumerate(zip(baseline,rows)):
            assert a['edge_flags']==b['edge_flags'],(i,a['edge_flags'],b['edge_flags'])
            assert a['exposure']==b['exposure'],(i,'Exposure mismatch')
            for domain in ('global',):
                for key in ('laplacian_variance','tenengrad'):
                    assert np.isclose(a['focus'][domain]['smoothed'][key],b['focus'][domain]['smoothed'][key],rtol=1e-9,atol=1e-14),(i,key)
            for ar,br in zip(a['focus']['regions'],b['focus']['regions']):
                assert ar['usable']==br['usable'] and ar['pixels']==br['pixels'],(i,ar['id'],'Region geometry')
                if ar['smoothed']:
                    for area in ('region','outside'):
                        am,bm=ar['smoothed'][area],br['smoothed'][area]
                        assert (am is None)==(bm is None)
                        if am:
                            assert am['pixels']==bm['pixels'],(i,ar['id'],area,'mask count')
                            for key in ('laplacian_variance','tenengrad'):
                                assert np.isclose(am[key],bm[key],rtol=1e-9,atol=1e-14),(i,ar['id'],area,key)
        # The standalone replay tool must reject changed pixels before completion.
        path=root/'pixels'/'0000-1024.rgba';path.write_bytes(b'changed')
        failed=subprocess.run([binary,str(root),str(root/'bad.jsonl')],capture_output=True,text=True,timeout=20)
        assert failed.returncode!=0 and 'Changed frozen pixels' in failed.stderr
    print('Passed 4 synthetic measurement comparisons and changed-pixel rejection')

if __name__=='__main__':
    run(sys.argv[1])
