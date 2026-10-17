"""Near-clipping diagnostics on exact 8-bit model views; no source image writes."""
from __future__ import annotations
import argparse, hashlib, html, json
from pathlib import Path
import cv2
import numpy as np

def clipping(rgb):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or not rgb.size:raise ValueError('Requires nonempty uint8 RGB')
    return {'near_white_all_channels_percent':float(100*np.mean(np.all(rgb>=254,axis=2))),
        'near_black_all_channels_percent':float(100*np.mean(np.all(rgb<=1,axis=2))),
        'high_any_channel_percent':float(100*np.mean(np.any(rgb>=254,axis=2))),
        'low_any_channel_percent':float(100*np.mean(np.any(rgb<=1,axis=2)))}

def region_pixels(rgb,box):
    h,w=rgb.shape[:2];x,y,bw,bh=box
    x0=max(0,min(w,int(np.floor(x*w))));x1=max(0,min(w,int(np.ceil((x+bw)*w))))
    y0=max(0,min(h,int(np.floor(y*h))));y1=max(0,min(h,int(np.ceil((y+bh)*h))))
    if x1<=x0 or y1<=y0:return None
    return rgb[y0:y1,x0:x1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--vision',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):raise ValueError('Private outputs must remain outside Git')
    result=json.loads(a.results.read_text());vision=json.loads(a.vision.read_text());native={(r['id'],r['max_dimension']):r for r in vision['rows'] if r.get('status')=='ok'};rows=[]
    for image in result['images']:
        view=a.results.parent/'model-views'/(image['id']+'-1024.png');digest=hashlib.sha256(view.read_bytes()).hexdigest()
        if digest!=result['transforms'][image['id']+'-1024']['sha256']:raise ValueError('Changed model view')
        bgr=cv2.imread(str(view));
        if bgr is None:raise ValueError('Undecodable model view')
        rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB);detection=native[(image['id'],1024)]
        if detection['path']!=image['path'] or (detection['width'],detection['height'])!=(rgb.shape[1],rgb.shape[0]):raise ValueError('Detection geometry mismatch')
        subjects=[]
        for name in ('face_quality','people','animals','attention','objectness'):
            request=detection['requests'][name]
            if request['status']!='ok':subjects.append({'kind':name,'status':'failed'});continue
            for index,o in enumerate(request['observations']):
                if 'box' not in o:continue
                pixels=region_pixels(rgb,o['box'])
                if pixels is None:subjects.append({'kind':name,'index':index,'status':'invalid_box'});continue
                subjects.append({'kind':name,'index':index,'box':o['box'],'pixels':pixels.shape[0]*pixels.shape[1],'status':'ok','clipping':clipping(pixels)})
        rows.append({'id':image['id'],'group':image['group'],'kind':image['kind'],'model_view_sha256':digest,'global':clipping(rgb),'subjects':subjects})
    groups={}
    for row in rows:
        if row['group']:groups.setdefault(row['group'],[]).append(row)
    ranges={gid:{metric:max(r['global'][metric] for r in group)-min(r['global'][metric] for r in group) for metric in group[0]['global']} for gid,group in groups.items()}
    a.output.mkdir(exist_ok=False,parents=True)
    data={'status':'complete','source_results_sha256':hashlib.sha256(a.results.read_bytes()).hexdigest(),'measurement':'Exact 8-bit upright sRGB 1024 model views; near endpoint pixels <=1 or >=254. Not RAW/sensor or source-TIFF clipping/recoverability.','automatic_cull_flags':False,'rows':rows,'within_group_global_ranges_percentage_points':ranges}
    (a.output/'results.json').write_text(json.dumps(data,indent=2));cards=[];images={i['id']:i for i in result['images']}
    for row in sorted(rows,key=lambda r:(r['group'] is None,r['group'] or '',r['id'])):
        g=row['global'];image=images[row['id']];faces=[s for s in row['subjects'] if s['kind']=='face_quality' and s['status']=='ok']
        face_text='; '.join(f'face {s["index"]+1}: white {s["clipping"]["near_white_all_channels_percent"]:.2f}%, black {s["clipping"]["near_black_all_channels_percent"]:.2f}%' for s in faces) or 'No face box: face exposure unassessed'
        cards.append(f'<article><h2>{html.escape(row["group"] or "Solo")} · {row["id"]}</h2><img src="data:image/jpeg;base64,{image["thumbnail"]}" alt="Local photograph"><p>Whole frame: near-white {g["near_white_all_channels_percent"]:.2f}%; near-black {g["near_black_all_channels_percent"]:.2f}%; any-channel highlights {g["high_any_channel_percent"]:.2f}%</p><p>{html.escape(face_text)}</p><details><summary>All subject measurements</summary><pre>{html.escape(json.dumps(row["subjects"],indent=2))}</pre></details></article>')
    (a.output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Exposure near-clipping diagnostic</title><style>body{font:16px system-ui;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:24px}img{width:100%}pre{white-space:pre-wrap}</style><h1>Exposure near-clipping diagnostic</h1><p>These are display-view endpoint measurements, not confirmed exposure faults or RAW recovery estimates. Bright backgrounds, reflections, silhouettes and scan borders can dominate whole-frame counts. No automatic cull decisions are made.</p><main>'+''.join(cards)+'</main>')
    print(json.dumps({'images':len(rows),'top_group_range_white':sorted([(g,v['near_white_all_channels_percent']) for g,v in ranges.items()],key=lambda x:-x[1])[:5],'top_group_range_black':sorted([(g,v['near_black_all_channels_percent']) for g,v in ranges.items()],key=lambda x:-x[1])[:5]},indent=2))
if __name__=='__main__':main()
