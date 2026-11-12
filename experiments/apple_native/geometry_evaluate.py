"""Local diagnostic of native registration; synthetic labels are construction facts.
Real corpus pairs retain algorithm provenance and are NOT human ground truth.
No residual threshold or production match decision is introduced.
"""
from __future__ import annotations

import argparse
import base64
import html
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from photo_utils.similarity import sift_pair


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def texture(seed):
    rng = np.random.default_rng(seed)
    image = np.full((480, 640, 3), 100, np.uint8)
    for _ in range(400):
        x, y = rng.integers([0, 0], [640, 480])
        color = tuple(int(v) for v in rng.integers(0, 256, 3))
        cv2.circle(image, (int(x), int(y)), int(rng.integers(2, 17)), color, -1)
    return image


def constructed_cases():
    a = texture(14)
    identity = np.eye(3)
    cases = []
    def add(name, b, transform, label='same_planar_content'):
        cases.append((name, a, b, transform, label))
    add('identity', a.copy(), identity)
    transforms = {
        'translation': np.array([[1., 0, 18], [0, 1, -12], [0, 0, 1]]),
        'rotation_4deg': np.vstack((cv2.getRotationMatrix2D((320, 240), 4, 1), [0, 0, 1])),
        'perspective': cv2.getPerspectiveTransform(np.float32([[0,0],[639,0],[639,479],[0,479]]),
                                                  np.float32([[20,14],[616,6],[635,465],[9,470]])),
    }
    for name, h in transforms.items():
        add(name, cv2.warpPerspective(a, h, (640, 480)), h)
    add('crop_unequal', a[40:440, 60:580].copy(), np.array([[1.,0,-60],[0,1,-40],[0,0,1]]))
    add('crop_rescaled', cv2.resize(a[40:440,60:580], (640,480)),
        np.array([[640/520,0,(-60+.5)*640/520-.5],[0,480/400,(-40+.5)*480/400-.5],[0,0,1]]))
    add('exposure', np.clip(a.astype(float)*.75+20,0,255).astype(np.uint8), identity)
    add('blur', cv2.GaussianBlur(a,(9,9),2), identity)
    burst_a=a.copy(); burst_b=a.copy()
    cv2.circle(burst_a,(300,220),35,(20,20,240),-1)
    cv2.circle(burst_b,(325,225),35,(20,20,240),-1)
    cases.append(('burst_motion_proxy',burst_a,burst_b,None,'same_synthetic_background_with_motion'))
    changed = a.copy(); changed[:,320:] = texture(28)[:,320:]
    add('half_content_changed', changed, None, 'changed_content')
    tiles = [a[y:y+240,x:x+320] for y in (0,240) for x in (0,320)]
    add('tiles_rearranged', np.vstack((np.hstack((tiles[3],tiles[2])),np.hstack((tiles[1],tiles[0])))), None,'changed_layout')
    add('unrelated', texture(42), None, 'different_construction')
    flat = np.full_like(a, 128)
    cases.append(('flat_identical',flat,flat.copy(),identity,'uninformative'))
    return cases


def features(image):
    gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    keys, descriptors = cv2.SIFT_create(nfeatures=500).detectAndCompute(gray,None)
    return {'points':np.asarray([k.pt for k in keys],np.float32), 'descriptors':descriptors,'shape':gray.shape}


def diagnostics(a,b,evidence,known):
    if evidence['status'] != 'ok':
        return {}
    # Vision matrix is floating -> reference in lower-left pixel coordinates.
    m = np.asarray(evidence['matrix_columns'],float).T
    if m.shape != (3,3) or not np.isfinite(m).all():
        raise ValueError('Invalid native matrix')
    fa = np.array([[1.,0,0],[0,-1,a.shape[0]-1],[0,0,1]])
    fb = np.array([[1.,0,0],[0,-1,b.shape[0]-1],[0,0,1]])
    h = fa @ m @ fb
    if abs(np.linalg.det(h)) < 1e-12:
        return {'singular':True}
    size = (a.shape[1],a.shape[0])
    aligned = cv2.warpPerspective(b,h,size)
    mask = cv2.warpPerspective(np.ones(b.shape[:2],np.uint8),h,size,flags=cv2.INTER_NEAREST)
    # Exclude interpolation edges and all padded canvas pixels from residual.
    mask = cv2.erode(mask,np.ones((5,5),np.uint8)).astype(bool)
    ga = cv2.cvtColor(a,cv2.COLOR_BGR2GRAY).astype(float)/255
    gb = cv2.cvtColor(aligned,cv2.COLOR_BGR2GRAY).astype(float)/255
    result = {'overlap_reference_fraction':float(mask.mean()),'matrix_top_left_b_to_a':h.tolist()}
    if mask.any():
        result['overlap_mae'] = float(np.abs(ga[mask]-gb[mask]).mean())
        x,y = ga[mask],gb[mask]
        denom = np.linalg.norm(x-x.mean())*np.linalg.norm(y-y.mean())
        result['overlap_ncc'] = float(np.dot(x-x.mean(),y-y.mean())/denom) if denom>1e-12 else None
    if known is not None:
        points = np.float32([[[x,y]] for y in (100,240,380) for x in (100,320,540)])
        target = cv2.perspectiveTransform(points,known)
        restored = cv2.perspectiveTransform(target,h)
        result['known_transform_median_error_pixels'] = float(np.median(np.linalg.norm(restored-points,axis=2)))
    return result


def write_review(output, rows):
    """Self-contained local inspection; labels are explicit user selections only."""
    cards=[]
    for row in rows:
        if row['mode'] != 'register-canvas':
            continue
        name=row['case']
        paths=[output/(name+'-'+suffix+'.png') for suffix in ('a','b')]
        images=[]
        h=row['diagnostics'].get('matrix_top_left_b_to_a')
        if h is not None:
            a,b=[cv2.imread(str(path)) for path in paths]
            aligned=cv2.warpPerspective(b,np.asarray(h),(a.shape[1],a.shape[0]))
            aligned_path=output/(name+'-aligned.png')
            if not cv2.imwrite(str(aligned_path),aligned):
                raise RuntimeError('Aligned preview output failed')
            paths.append(aligned_path)
        for caption,path in zip(('Reference','Floating','Native aligned floating'),paths):
            data=base64.b64encode(path.read_bytes()).decode('ascii')
            images.append('<figure><figcaption>'+caption+'</figcaption><img src="data:image/png;base64,'+data+'"></figure>')
        selection=''
        if row['label']=='unjudged':
            selection='<label>Manual review <select data-case="'+html.escape(name)+'"><option value="unjudged">Unjudged</option><option value="related">Related views for grouping</option><option value="unrelated">Unrelated for grouping</option><option value="uncertain">Uncertain</option></select></label>'
        details={k:v for k,v in row['diagnostics'].items() if k!='matrix_top_left_b_to_a'}
        cards.append('<article><h2>'+html.escape(name)+'</h2><p>'+html.escape(row['label_provenance']+'; '+row['label'])+'</p><p>Native confidence: '+str(row['evidence'].get('confidence'))+'; accepted SIFT candidate: '+str(row['sift']['sift_candidate'])+'</p><div class="images">'+''.join(images)+'</div><pre>'+html.escape(json.dumps(details,indent=2))+'</pre>'+selection+'</article>')
    binding=json.dumps({'summary_sha256':digest(output/'summary.json')})
    document='<!doctype html><meta charset="utf-8"><title>Native geometry evaluation</title><style>body{font:16px system-ui;margin:32px;max-width:1400px;background:#f5f5f5;color:#222}article{background:white;padding:20px;margin:24px 0}h1{font-size:28px}.images{display:flex;gap:12px}figure{margin:0;flex:1;min-width:0}img{width:100%}select,button{font:inherit;padding:8px}pre{white-space:pre-wrap}</style><h1>Native geometry evaluation</h1><p>Diagnostic only. A matrix, confidence or low residual is not a match verdict. Synthetic labels describe construction; real-photo controls remain unjudged. Aligned previews can contain black borders. Originals are unchanged.</p><p>Optional manual choices stay in this page until you download them. No server or network requests.</p><button id="export">Download manual labels</button>'+''.join(cards)+"<script>document.getElementById('export').onclick=()=>{const rows=[...document.querySelectorAll('select')].map(s=>({case:s.dataset.case,label:s.value}));const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({scope:'Explicit manual review; unjudged remains unjudged',binding:window.evaluationBinding,rows},null,2)],{type:'application/json'}));a.download='geometry-manual-labels.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};</script>"
    document += '<script>window.evaluationBinding='+binding+';</script>'
    (output/'review.html').write_text(document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--corpus',type=Path,help='Existing comparison inventory and pairs; optional')
    parser.add_argument('--fixture',type=Path,help='Frozen RGBA fixture required with corpus')
    args = parser.parse_args()
    if bool(args.corpus) != bool(args.fixture):
        parser.error('--corpus and --fixture must be supplied together')
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    args.output.chmod(0o700)
    rows = []
    binary = args.binary.resolve(); binary_hash = digest(binary)
    def evaluate(name,a,b,known,label,provenance,baseline=None):
        paths = [args.output/(name+'-'+suffix+'.png') for suffix in ('a','b')]
        for path,image in zip(paths,(a,b)):
            if not cv2.imwrite(str(path),image):
                raise RuntimeError('PNG output failed')
        hashes = [digest(p) for p in paths]
        sift = sift_pair(features(a),features(b),cv2.BFMatcher(cv2.NORM_L2))
        for mode in ('register','register-canvas'):
            started = time.perf_counter()
            try:
                process = subprocess.run([str(binary),mode,*map(str,paths)],capture_output=True,text=True,timeout=60)
                evidence = json.loads(process.stdout) if process.returncode==0 else {'status':'failed','error':process.stderr}
            except subprocess.TimeoutExpired:
                evidence = {'status':'timeout'}
            row = {'case':name,'mode':mode,'label':label,'label_provenance':provenance,
                   'sift':sift,'baseline_pair':baseline,'evidence':evidence,'seconds':time.perf_counter()-started,
                   'input_png_sha256':hashes, 'diagnostics':diagnostics(a,b,evidence,known)}
            rows.append(row)
            with (args.output/'rows.jsonl').open('a') as file:
                file.write(json.dumps(row,allow_nan=False)+'\n')
        if hashes != [digest(p) for p in paths]:
            raise RuntimeError('Evaluation inputs changed')
    for name,a,b,h,label in constructed_cases():
        evaluate(name,a,b,h,label,'deterministic construction, not photographic annotation')
    sources = {}
    if args.corpus:
        sources = json.loads((args.corpus/'inventory.json').read_text())
        pairs = json.loads((args.corpus/'pairs.json').read_text())
        paths = list(sources)
        complete = json.loads((args.fixture/'complete.json').read_text())
        for name, expected in complete['files'].items():
            if digest(args.fixture/name) != expected:
                raise RuntimeError('Frozen fixture metadata changed')
        views = json.loads((args.fixture/'views.json').read_text())
        inventory = json.loads((args.fixture/'inventory.json').read_text())
        if inventory != sources:
            raise RuntimeError('Comparison and fixture inventories differ')
        # Frozen fixture completion/measurement harness is the authority for view bytes.
        print('Loading corpus views',flush=True)
        selected = [('sift_only',p) for p in pairs if p['baseline_level']!='unmatched' and p['vision_only_level']=='unmatched']
        selected += [('vision_supported',p) for p in pairs if p['vision_only_level']=='likely'][:3]
        selected += [('baseline_unmatched',p) for p in pairs if p['baseline_level']=='unmatched'][:3]
        selected_paths = {paths[p[k]] for _,p in selected for k in ('a','b')}
        def verify_sources():
            for path in selected_paths:
                if digest(Path(path)) != sources[path]:
                    raise RuntimeError('Original changed or missing')
        verify_sources()
        for kind,pair in selected:
            images=[]
            for key in ('a','b'):
                index=pair[key]
                view=next(v for v in views if v['index']==index and v['max_dimension']==1024)
                if view['path'] != paths[index]:
                    raise RuntimeError('Fixture identity mismatch')
                pixel=args.fixture/'pixels'/f'{index:04d}-1024.rgba'
                # Match the exact frozen pixel hash, not only the original file.
                if digest(pixel) != complete['pixels_sha256'][pixel.name]:
                    raise RuntimeError('Frozen pixels changed')
                rgba=np.frombuffer(pixel.read_bytes(),np.uint8).reshape(view['height'],view['width'],4)
                images.append(cv2.cvtColor(rgba,cv2.COLOR_RGBA2BGR))
            evaluate(f'{kind}-{pair["a"]}-{pair["b"]}',*images,None,'unjudged',
                     'algorithm-selected control; human label absent',pair)
        verify_sources()
    if digest(binary)!=binary_hash:
        raise RuntimeError('Binary changed during evaluation')
    summary={'cases':len(rows)//2,'runs':len(rows),'binary_sha256':binary_hash,
             'adapter_sha256':digest(Path(__file__)), 'python_version':sys.version,
             'opencv_version':cv2.__version__, 'numpy_version':np.__version__, 'platform':platform.platform(),
             'source_checksums_unchanged':True,'rows':rows,
             'scope':'No match classifier, no threshold tuning; synthetic labels and unjudged corpus controls remain separate.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    write_review(args.output, rows)
    print(json.dumps({'cases':summary['cases'],'runs':len(rows),'statuses':{mode:{status:sum(r['mode']==mode and r['evidence']['status']==status for r in rows) for status in sorted({r['evidence']['status'] for r in rows})} for mode in ('register','register-canvas')}},indent=2))


if __name__ == '__main__':
    main()
