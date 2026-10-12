"""Diagnostic region focus using cached Vision boxes and the shared focus engine."""
import argparse
import base64
import copy
import html
import json
from pathlib import Path
import subprocess
import tempfile

import cv2
import numpy as np

from quality import focus_fields
from run import digest
from subject_audit import render, validate_regions

VERSION='region-focus-v1'


def box_mask(box, shape):
    height,width=shape
    x,y,w,h=box
    left,top=max(0,int(x*width)),max(0,int(y*height))
    right,bottom=min(width,round((x+w)*width)),min(height,round((y+h)*height))
    mask=np.zeros(shape,np.uint8)
    mask[top:bottom,left:right]=1
    return mask,(right-left,bottom-top)


def masked_metrics(fields, mask):
    # Derivatives are computed before masking; guard pixels prevent sampling
    # crop/mask boundaries as artificial edges.
    selected=cv2.erode(mask,np.ones((3,3),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
    count=int(selected.sum())
    if count<100:return None
    gray,laplacian,energy=fields
    return {'pixels':count,'laplacian_variance':float(laplacian[selected].var()),
            'tenengrad':float(energy[selected].mean()), 'gradient_energy_p90':float(np.quantile(energy[selected],.9)),
            'luminance_mean':float(gray[selected].mean()),'luminance_std':float(gray[selected].std())}


def analyze_regions(rgb,detectors,treatment='gaussian1'):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    filters={'raw':lambda:gray,'gaussian1':lambda:cv2.GaussianBlur(gray,(0,0),1.),
             'gaussian2':lambda:cv2.GaussianBlur(gray,(0,0),2.),
             'bilateral':lambda:cv2.bilateralFilter(gray,5,15,2)}
    if treatment not in filters:raise ValueError('Unknown focus treatment')
    raw=focus_fields(gray)
    fields={'raw':raw,'smoothed':raw if treatment=='raw' else focus_fields(filters[treatment]())}
    excluded=np.zeros(gray.shape,np.uint8)
    for kind in ('faces','people','animals'):
        for region in detectors[kind].get('regions',[]):
            mask,_=box_mask(region.get('display_box',region['box']),gray.shape)
            excluded |= mask
    global_mask=np.ones(gray.shape,np.uint8)
    global_values={t:masked_metrics(f,global_mask) for t,f in fields.items()}
    tile_values=[]
    for ys in np.array_split(np.arange(gray.shape[0]),4):
        for xs in np.array_split(np.arange(gray.shape[1]),4):
            mask=np.zeros(gray.shape,np.uint8)
            mask[ys[0]:ys[-1]+1,xs[0]:xs[-1]+1]=1
            value=masked_metrics(fields['smoothed'],mask)
            if value:tile_values.append(value['tenengrad'])
    regions=[]
    for kind in ('faces','people','animals','objectness','attention'):
        detector=detectors[kind]
        for index,region in enumerate(detector.get('regions',[]),1):
            mask,size=box_mask(region.get('display_box',region['box']),gray.shape)
            outside=1-cv2.dilate(excluded|mask,np.ones((7,7),np.uint8))
            result={'id':f'{kind} {index}','box':region['box'],'pixels':list(size),
                    'usable':min(size)>=24,'raw':None,'smoothed':None}
            if result['usable']:
                for treatment,f in fields.items():
                    inside=masked_metrics(f,mask);background=masked_metrics(f,outside)
                    ratios={}
                    if inside and background:
                        for metric in ('laplacian_variance','tenengrad','gradient_energy_p90'):
                            ratios[metric]=inside[metric]/background[metric] if background[metric]>0 else None
                    result[treatment]={'region':inside,'outside':background,'region_to_outside':ratios}
            regions.append(result)
            region['focus']=result
    return {'version':VERSION,'treatment':treatment,'sigma':{'gaussian1':1.,'gaussian2':2.}.get(treatment),
            'bilateral_parameters':{'d':5,'sigmaColor':15,'sigmaSpace':2} if treatment=='bilateral' else None,'minimum_region_side':24,
            'outside_definition':'Outside this region and every detected face/person/animal box, with a 3px guard; may contain missed subjects.',
            'global':global_values,'tile_tenengrad':tile_values,'regions':regions}


def table(focus):
    esc=html.escape
    parts=['<table><tr><th>Region</th><th>Size</th><th>Smoothed Laplacian region / outside</th>'
           '<th>Smoothed Tenengrad region / outside</th><th>T ratio raw → smoothed</th></tr>']
    for region in focus['regions']:
        smoothed=region['smoothed'];raw=region['raw']
        name=esc(region['id']);size='×'.join(map(str,region['pixels']))
        if not smoothed or not smoothed['region']:
            parts.append(f'<tr><td>{name}</td><td>{size}</td><td colspan="3">Too small to measure reliably</td></tr>');continue
        inside,outside=smoothed['region'],smoothed['outside']
        def pair(metric):
            return f'{inside[metric]:.5g} / {outside[metric]:.5g}' if outside else f'{inside[metric]:.5g} / unavailable'
        def ratio(row):
            value=row['region_to_outside'].get('tenengrad') if row else None
            return f'{value:.3f}' if value is not None else 'unavailable'
        parts.append(f'<tr><td>{name}</td><td>{size}</td><td>{pair("laplacian_variance")}</td><td>{pair("tenengrad")}</td>'
                     f'<td>{ratio(raw)} → {ratio(smoothed)}</td></tr>')
    parts.append('</table><p>A ratio below 1 means less measured edge detail inside the region than outside. '
                 'Texture, contrast, grain and region size affect this comparison; it is not a blur verdict. '
                 '“Outside” can contain subjects the detector missed.</p>')
    return '\n'.join(parts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',required=True,type=Path)
    parser.add_argument('--helper',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args()
    audit=json.loads(args.audit.read_text())
    paths=[Path(p) for p in audit['source_paths']]
    hashes=audit['source_sha256']
    if any(p.is_symlink() for p in paths) or hashes!=[digest(p) for p in paths]:raise ValueError('Audit sources changed')
    stats=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    output=args.output_dir.resolve();repository=Path(__file__).resolve().parents[2]
    if output==repository or repository in output.parents or any(output==p.parent or p.parent in output.parents for p in paths):
        raise ValueError('Output must be outside originals and repository')
    rows=[];completed=False
    cached=audit['rows']
    with tempfile.TemporaryFile() as stream:
        process=subprocess.run([str(args.helper.resolve()),'--pixels-only'],input=json.dumps(list(map(str,paths))).encode(),
                               stdout=stream,stderr=subprocess.PIPE,timeout=180)
        if process.returncode:raise RuntimeError(process.stderr.decode(errors='replace'))
        stream.seek(0)
        for line in stream:
            pixels=json.loads(line)
            if completed:raise ValueError('Unexpected output after completion')
            if pixels['type']=='complete':completed=pixels['images']==len(paths);continue
            if len(rows)>=len(cached):raise ValueError('Extra decoded image')
            row=copy.deepcopy(cached[len(rows)])
            for key in ('index','path','max_dimension','width','height'):
                if row[key]!=pixels[key]:raise ValueError('Decode/detection geometry mismatch')
            validate_regions(row['detectors'])
            w,h=row['width'],row['height']
            rgb=np.frombuffer(base64.b64decode(pixels['rgba'],validate=True),np.uint8).reshape(h,w,4)[:,:,:3]
            row['focus']=analyze_regions(rgb,row['detectors'])
            ok,encoded=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90])
            if not ok:raise ValueError('Preview encoding failed')
            row['thumbnail']=base64.b64encode(encoded.tobytes()).decode('ascii');rows.append(row)
    if not completed or len(rows)!=len(cached):raise ValueError('Incomplete decoding')
    document=render(rows,{},output/'region-focus.html')
    document=document.replace('<h1>Subject detection audit</h1>','<h1>Subject-region focus experiment</h1><p>Boxes reuse the subject audit. Focus now uses fresh native pixels and the shared Laplacian/Tenengrad engine. Compare faces first, then body/animal and objectness regions; keep co-primary subjects visible. Attention is a broader context region. No regions are discarded or collapsed into a single winning subject.</p>')
    for row in rows:
        heading=f'<h3>{row["max_dimension"]}-pixel detection ({row["width"]}×{row["height"]})</h3>'
        start=document.index(f'<section><h2>{html.escape(Path(row["path"]).name)}</h2>')
        pos=document.index(heading,start)+len(heading)
        document=document[:pos]+table(row['focus'])+document[pos:]
    if hashes!=[digest(p) for p in paths] or stats!=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]:raise ValueError('Sources changed')
    output.mkdir(parents=True,exist_ok=False)
    (output/'region-focus.html').write_text(document)
    payload={'version':VERSION,'audit_sha256':digest(args.audit),'source_paths':list(map(str,paths)),
             'source_sha256':hashes,'inputs_unchanged':True,'measurement_source_sha256':digest(Path(__file__).with_name('quality.py')),
             'helper_sha256':digest(args.helper),'rows':[{k:v for k,v in r.items() if k!='thumbnail'} for r in rows]}
    (output/'region-focus.json').write_text(json.dumps(payload,indent=2))
    print('Saved:',output/'region-focus.html')


if __name__=='__main__':main()
