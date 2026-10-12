"""Subject-patch safeguards, fixed-size regions and primary-subject ablations."""
import argparse,base64,csv,html,json,subprocess,tempfile
from pathlib import Path
import cv2
import numpy as np
from edge_blur import extract,summarize
from run import digest

PARAMETERS={'grid':5,'minimum_profiles':20,'minimum_contrast':.1,'maximum_width':3.,'maximum_soft_fraction':.4,'minimum_connected_patches':3,'minimum_orientations':2,'primary_area_fraction':.25,'standardized_face_long_side':128,'standardized_other_long_side':256,'scale_requirement':'both 1024 and 2048; no upscaling'}


def connected_sharp(cells):
    remaining={tuple(c['cell']) for c in cells if c['sharp']}
    while remaining:
        start=remaining.pop();group={start};todo=[start]
        while todo:
            x,y=todo.pop()
            for q in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if q in remaining:remaining.remove(q);group.add(q);todo.append(q)
        if len(group)>=PARAMETERS['minimum_connected_patches']:return True
    return False


def measure(gray,box,kind,standardized):
    h,w=gray.shape;x,y,bw,bh=box
    x0=max(0,int(x*w));y0=max(0,int(y*h));x1=min(w,int(np.ceil((x+bw)*w)));y1=min(h,int(np.ceil((y+bh)*h)))
    if x1<=x0 or y1<=y0:return {'supported':False,'sharp':False,'cells':[]}
    target=128 if kind=='faces' else 256
    factor=min(1,target/max(x1-x0,y1-y0)) if standardized else 1.
    # Downsample context with the subject, preserving profile margins around ROI.
    cx0=max(0,x0-int(np.ceil(20/factor)));cy0=max(0,y0-int(np.ceil(20/factor)))
    cx1=min(w,x1+int(np.ceil(20/factor)));cy1=min(h,y1+int(np.ceil(20/factor)))
    crop=gray[cy0:cy1,cx0:cx1]
    if factor<1:crop=cv2.resize(crop,(max(1,round(crop.shape[1]*factor)),max(1,round(crop.shape[0]*factor))),interpolation=cv2.INTER_AREA)
    sx=crop.shape[1]/(cx1-cx0);sy=crop.shape[0]/(cy1-cy0)
    local=[(x0-cx0)*sx/crop.shape[1],(y0-cy0)*sy/crop.shape[0],(x1-x0)*sx/crop.shape[1],(y1-y0)*sy/crop.shape[0]]
    edges=extract(crop,stride=1,maximum_edges=10000)
    valid=(np.asarray(edges['contrast'])>=PARAMETERS['minimum_contrast']) & ~np.asarray(edges['censored'],dtype=bool)
    edges={k:np.asarray(v)[valid].tolist() for k,v in edges.items()}
    cells=[]
    for iy in range(5):
        for ix in range(5):
            cb=[local[0]+ix*local[2]/5,local[1]+iy*local[3]/5,local[2]/5,local[3]/5]
            m=summarize(edges,cb,crop.shape)
            ex=np.asarray(edges['x'])/crop.shape[1];ey=np.asarray(edges['y'])/crop.shape[0]
            select=(ex>=cb[0])&(ex<cb[0]+cb[2])&(ey>=cb[1])&(ey<cb[1]+cb[3])
            angles=np.asarray(edges['angle'])[select];bins=np.floor(angles/(np.pi/4)).astype(int)%4
            orientation_count=sum(np.count_nonzero(bins==b)>=5 for b in range(4))
            sharp=m['edges']>=20 and m['median_width']<3 and m['contrast_soft_fraction']<.4 and orientation_count>=2
            cells.append({'cell':[ix,iy],'sharp':bool(sharp),'metrics':m,'orientation_count':orientation_count})
    return {'supported':any(c['metrics']['edges']>=20 for c in cells),'sharp':connected_sharp(cells),'cells':cells,'resize_factor':factor}


def select_subjects(detectors):
    regions=[]
    faces=detectors['faces'].get('regions',[])
    for kind in ('faces','people','animals'):
        for i,r in enumerate(detectors[kind].get('regions',[]),1):
            box=r.get('display_box',r['box'])
            # A person containing a detected face is represented by that face;
            # clothing cannot rescue the corresponding blurred face.
            if kind=='people' and any(box[0]<=f['box'][0]+f['box'][2]/2<=box[0]+box[2] and box[1]<=f['box'][1]+f['box'][3]/2<=box[1]+box[3] for f in faces):continue
            regions.append({'id':f'{kind} {i}','kind':kind,'box':box})
    if not regions:
        for kind in ('objectness','attention'):
            boxes=detectors[kind].get('regions',[])
            if boxes:
                regions=[{'id':f'{kind} {i}','kind':kind,'box':r.get('display_box',r['box'])} for i,r in enumerate(boxes,1)];break
    return regions


def primary_ids(regions):
    result=set()
    for kind in ('faces','people','animals','objectness','attention'):
        group=[r for r in regions if r['kind']==kind]
        biggest=max((r['box'][2]*r['box'][3] for r in group),default=0)
        result.update(r['id'] for r in group if r['box'][2]*r['box'][3]>=biggest*.25)
    return result


def subject_sharp(rows,method,primary=False):
    return all(r['subjects'] and all(s[method]['sharp'] for s in r['subjects'] if not primary or s['primary']) for r in rows)


def combine(baseline,global_flag,fallback,veto):
    return bool(baseline or fallback or (global_flag and not veto))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--helper',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();out=a.output_dir.resolve()
    if out.exists():raise ValueError('Output exists')
    repo=Path(__file__).resolve().parents[2]
    if out==repo or repo in out.parents:raise ValueError('Output must be outside repo')
    edge=json.loads((a.parent/'EdgeBlur-both-sets-trial-01/measurements.json').read_text());samples={r['sample']['path']:r['sample'] for r in edge['records']}
    hashes={path:digest(Path(path)) for path in samples};stats={path:(Path(path).stat().st_size,Path(path).stat().st_mtime_ns) for path in samples}
    if hashes!=edge['source_sha256']:raise ValueError('Changed source')
    metadata={};geometry={}
    for folder in ('FocusTests','FocusTests2'):
        audit=json.loads((a.parent/(folder+'-subjects-trial-01')/'subjects.json').read_text());metadata.update({(r['path'],r['max_dimension']):r for r in audit['rows']})
        bench=json.loads((a.parent/(folder+'-benchmark-trial-01')/'benchmark.json').read_text());geometry.update({(r['path'],r['max_dimension']):(r['width'],r['height']) for r in bench['measurements']['gaussian1']})
    records=[];previews={};paths=list(samples)
    with tempfile.TemporaryFile() as stream:
        proc=subprocess.run([str(a.helper.resolve()),'--pixels-only'],input=json.dumps(paths).encode(),stdout=stream,stderr=subprocess.PIPE,timeout=600)
        if proc.returncode:raise RuntimeError(proc.stderr.decode())
        stream.seek(0);complete=False;count=0
        for line in stream:
            row=json.loads(line)
            if row['type']=='complete':complete=row['images']==len(paths);continue
            path=paths[count//2];scale=(1024,2048)[count%2];count+=1
            if (row['path'],row['index'],row['max_dimension'])!=(path,(count-1)//2,scale):raise ValueError('Output order mismatch')
            w,h=row['width'],row['height']
            if (w,h)!=geometry[path,scale]:raise ValueError('Decode geometry mismatch')
            rgb=np.frombuffer(base64.b64decode(row['rgba'],validate=True),np.uint8).reshape(h,w,4)[:,:,:3];gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
            subjects=select_subjects(metadata[path,scale]['detectors']);primary=primary_ids(subjects)
            for subject in subjects:
                subject['primary']=subject['id'] in primary
                subject['native']=measure(gray,subject['box'],subject['kind'],False)
                subject['standardized']=measure(gray,subject['box'],subject['kind'],True)
            records.append({'path':path,'scale':scale,'subjects':subjects})
            if scale==1024:
                ok,jpg=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90]);assert ok
                previews[path]=base64.b64encode(jpg).decode()
            if count%20==0:print('Measured',count//2,'/',len(paths),flush=True)
    if not complete or count!=len(paths)*2:raise ValueError('Incomplete output')
    decisions=[]
    for old in edge['decisions']:
        path=old['path'];rows=[r for r in records if r['path']==path];er=[r for r in edge['records'] if r['sample']['path']==path]
        semantic=any(r['id'].split()[0] in ('faces','people','animals') for row in er for r in row['regions'])
        fallback=not semantic and any(r['id'].startswith('objectness') and r['metrics']['sufficient'] and r['metrics']['contrast_soft_fraction']>=.6 for row in er for r in row['regions'])
        baseline=old['baseline'];global_flag=old['contrast_proxy'];original=combine(baseline,global_flag,fallback,False)
        native=subject_sharp(rows,'native');normalized=subject_sharp(rows,'standardized');primary=subject_sharp(rows,'standardized',True)
        # Borderline global trigger: exactly one input scale triggers and every
        # matched semantic subject is supported and below the contrast boundary
        # at both scales. No-face regional fallback is never cleared by this.
        stable=all(row['subjects'] and all(s['kind'] in ('faces','people','animals') and any(r['id']==s['id'] and r['metrics']['sufficient'] and r['metrics']['contrast_soft_fraction']<.6 for r in next(o for o in er if o['scale']==row['scale'])['regions']) for s in row['subjects']) for row in rows)
        borderline=global_flag and sum(r['flags']['contrast_proxy'] for r in er)==1 and stable
        d={'path':path,'baseline_review':baseline,'global_contrast_review':global_flag,'regional_fallback_review':fallback,'previous_combined_review':original,
           'native_patch_review':combine(baseline,global_flag,fallback,native),'standardized_patch_review':combine(baseline,global_flag,fallback,normalized),
           'primary_subject_review':combine(baseline,global_flag,fallback,primary),'cross_scale_confirmation_review':combine(baseline,global_flag,fallback,borderline),
           'final_review':combine(baseline,global_flag,fallback,native or normalized or primary or borderline),
           'sharp_native':native,'sharp_standardized':normalized,'sharp_primary':primary,'borderline_cleared':borderline}
        decisions.append(d)
    groups=json.loads((a.parent/'EdgeBlur-both-sets-trial-01/user-review-feedback-v1.json').read_text())['groups']
    groups['first_set_explicit_focus_misses']=['000097550006.jpg','000355610007.jpg','000355610008.jpg','000438810032.jpg']
    summary={g:{key:sum(d[key] for d in decisions if Path(d['path']).name in names) for key in ('previous_combined_review','native_patch_review','standardized_patch_review','primary_subject_review','cross_scale_confirmation_review','final_review')} for g,names in groups.items()}
    esc=html.escape;yes=lambda b:'Yes' if b else 'No'
    columns=[('baseline_review','Baseline'),('global_contrast_review','Global contrast'),('regional_fallback_review','Regional fallback'),('previous_combined_review','Previous combined'),('native_patch_review','With sharp patches'),('standardized_patch_review','With size normalization'),('primary_subject_review','With primary subjects'),('cross_scale_confirmation_review','With scale confirmation'),('final_review','Final review')]
    page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Subject sharp-detail review</title><style>body{font:16px system-ui;max-width:1400px;margin:auto;padding:22px;background:#f6f5f0}section{background:white;margin:24px 0;padding:18px}svg{width:100%;max-width:1050px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:left}th{font-size:14px}.yes{background:#ffe5df}.no{background:#e6f3e7}.final{font-weight:bold}a{color:#245b88}label{margin-right:12px}p{line-height:1.5}.table{overflow-x:auto}</style>',
    '<h1>Sharp subject detail: both focus sample sets</h1><p>Each column answers “Does this test suggest review?” Yes means review; No does not certify focus. The first three columns are individual triggers. Each “With…” column applies one safeguard to the previous combination. Final review applies all safeguards together. A safeguard can clear new global-contrast flags only; baseline flags and no-semantic-subject regional fallback remain protected.</p>',
    '<p>Sharp patches require connected, supported patches with narrow contrast-rich edges in more than one direction. Size normalization downsamples subject regions to a common size and never enlarges them. Primary-subject testing excludes much smaller detections of the same type; this is an experimental size heuristic, not a semantic determination. A detected face represents its enclosing person so sharp clothing cannot rescue a blurred face. Every retained subject must qualify at both image sizes. Scale confirmation clears a single-scale global trigger only when supported semantic regions stay below the contrast trigger at both scales.</p>',
    '<p>Development-set experiment, not a changed working rule. Unknown or sparse evidence cannot clear a flag. Overlays use the original cached detections; focused background detail inside a rectangular box can still confuse a patch test.</p>',
    '<p>Boxes: <span style="color:#df2535">faces</span>, <span style="color:#238d49">people</span>, <span style="color:#d88100">animals</span>, <span style="color:#7558d1">objectness</span>, <span style="color:#008ca0">attention</span>. Dashed white boxes mark subjects retained by the primary-subject experiment.</p>',
    '<p><label><input id="boxes" type="checkbox" checked>Show detection boxes</label><label><input id="primary" type="checkbox" checked>Show primary boxes</label><label><input id="changed" type="checkbox">Only results changed from previous combination</label></p>']
    for folder in ('FocusTests','FocusTests2'):
        subset=[d for d in decisions if Path(d['path']).parent.name==folder]
        page.append(f'<h2>{folder}</h2>')
        for d in subset:
            path=d['path'];name=Path(path).name;m=metadata[path,1024];w,h=m['width'],m['height']
            page.append(f'<section id="{esc(name)}" data-changed="{str(d["final_review"]!=d["previous_combined_review"]).lower()}"><h3>{esc(name)}</h3><p>{esc(samples[path]["notes"] or "Awaiting review / see previous user feedback")}</p><div class="table"><table><tr>'+''.join('<th>'+label+'</th>' for _,label in columns)+'</tr><tr>'+''.join(f'<td class="{"yes" if d[k] else "no"} {"final" if k=="final_review" else ""}">{yes(d[k])}</td>' for k,_ in columns)+'</tr></table></div>')
            page.append(f'<svg viewBox="0 0 {w} {h}"><image width="{w}" height="{h}" href="data:image/jpeg;base64,{previews[path]}"/><g class="detections">')
            colors={'faces':'#ff3044','people':'#24dd67','animals':'#ffa700','objectness':'#ad7dff','attention':'#00d9ed'}
            for kind in colors:
                for i,r in enumerate(m['detectors'][kind].get('regions',[]),1):
                    x,y,bw,bh=r.get('display_box',r['box']);page.append(f'<rect x="{x*w}" y="{y*h}" width="{bw*w}" height="{bh*h}" fill="none" stroke="{colors[kind]}" stroke-width="2"/><text x="{x*w+3}" y="{max(14,y*h+14)}" fill="{colors[kind]}" stroke="black" stroke-width=".3" font-size="13">{kind} {i}</text>')
            page.append('</g><g class="primary">')
            for s in next(r for r in records if r['path']==path and r['scale']==1024)['subjects']:
                if s['primary']:
                    x,y,bw,bh=s['box'];page.append(f'<rect x="{x*w}" y="{y*h}" width="{bw*w}" height="{bh*h}" fill="none" stroke="white" stroke-dasharray="5 4"/>')
            page.append('</g></svg></section>')
    page.append('<script>function update(){document.querySelectorAll(".detections").forEach(e=>e.style.display=document.getElementById("boxes").checked?"":"none");document.querySelectorAll("g.primary").forEach(e=>e.style.display=document.getElementById("primary").checked?"":"none");document.querySelectorAll("section").forEach(e=>e.hidden=document.getElementById("changed").checked&&e.dataset.changed!=="true")}document.querySelectorAll("input").forEach(e=>e.addEventListener("change",update));</script></html>')
    for path,sha in hashes.items():
        q=Path(path)
        if digest(q)!=sha or (q.stat().st_size,q.stat().st_mtime_ns)!=stats[path]:raise ValueError('Source changed')
    out.mkdir(parents=True,exist_ok=False);(out/'report.html').write_text('\n'.join(page))
    (out/'measurements.json').write_text(json.dumps({'parameters':PARAMETERS,'records':records,'decisions':decisions,'summary':summary,'source_sha256':hashes,'inputs_unchanged':True,'implementation_sha256':{q.name:digest(q) for q in (Path(__file__),Path(__file__).with_name('edge_blur.py'))}},indent=2))
    with (out/'results.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['path']+[k for k,_ in columns]);writer.writeheader();writer.writerows({k:d[k] for k in writer.fieldnames} for d in decisions)
    print(json.dumps(summary,indent=2));print('Changed:',[Path(d['path']).name for d in decisions if d['final_review']!=d['previous_combined_review']]);print('Saved',out/'report.html')

if __name__=='__main__':main()
