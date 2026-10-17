"""Explicit private diagnostic export; no production/database writes."""
from __future__ import annotations
import argparse, hashlib, html, json, subprocess, time
from pathlib import Path

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--solos',type=Path,required=True);p.add_argument('--helper',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--exclude-baseline-index',type=int,action='append',default=[])
    a=p.parse_args();repo=Path(__file__).resolve().parents[3]
    if a.output.resolve().is_relative_to(repo):raise ValueError('Private outputs must be outside repository')
    a.output.mkdir(exist_ok=False,parents=True)
    base=json.loads(a.baseline.read_text());solo=json.loads(a.solos.read_text())
    members={i for g in solo['groups'] for i in g['members']}
    candidates=[i for i in range(len(solo['images'])) if i not in members and Path(solo['images'][i]['path']).is_file()]
    chosen=candidates[::max(1,len(candidates)//30)][:30]
    records=[]
    groups={i:g.get('id',f'group-{n:03}') for n,g in enumerate(base['groups']) for i in g['members']}
    for source,indices,kind in [(base,range(len(base['images'])),'grouped'),(solo,chosen,'solo')]:
      for i in indices:
        if source is base and i in a.exclude_baseline_index:continue
        image=source['images'][i];path=Path(image['path'])
        if not path.is_file():raise ValueError(f'Missing original: {path}')
        checksum=digest(path) if path.is_file() else None
        hashes=source.get('hashes',{})
        expected=image.get('sha256') or (hashes[i] if isinstance(hashes,list) else hashes.get(str(path)))
        if checksum and expected and expected!=checksum:raise ValueError(f'Changed original: {path}')
        records.append({'id':f'image-{len(records):03}', 'path':str(path),'sha256':checksum,'group':groups.get(i) if kind=='grouped' else None,'kind':kind,'thumbnail':image.get('thumbnail',''),'baseline_index':i,'existing_assets':image.get('existing_assets',[]),'focus_review':image.get('focus_review')})
    def save(name,data):
        tmp=a.output/(name+'.partial');tmp.write_text(json.dumps(data,indent=2));tmp.replace(a.output/name)
    save('manifest.json',{'status':'running','images':records,'baseline':str(a.baseline),'solos':str(a.solos),'helper_sha256':digest(a.helper)})
    start=time.monotonic();rows=[]
    try:
      # One image per subprocess bounds memory and makes every completed image durable.
      for index,image in enumerate(records):
        run=subprocess.run([str(a.helper)],input=json.dumps([image['path']]),capture_output=True,text=True,timeout=120,check=True)
        native=[json.loads(line) for line in run.stdout.splitlines()]
        if len(native)!=3 or native[-1].get('type')!='complete' or native[-1].get('images')!=1:raise ValueError('Incomplete native output')
        if {r.get('max_dimension') for r in native[:-1]}!={1024,2048} or any(r.get('path')!=image['path'] or r.get('index')!=0 for r in native[:-1]):raise ValueError('Native identity mismatch')
        for row in native[:-1]:row['index']=index;row['id']=image['id'];rows.append(row)
        save('vision-results.json',{'status':'running','rows':rows,'seconds':time.monotonic()-start})
        if any(r.get('status')!='ok' or any(v.get('status')!='ok' for v in r.get('requests',{}).values()) for r in native[:-1]):raise ValueError('Native Vision analysis failed; dependent run stopped')
        print(f'Vision {index+1}/{len(records)}',flush=True)
      if any(digest(Path(r['path']))!=r['sha256'] for r in records if r['sha256']):raise ValueError('Original changed during run')
      save('vision-results.json',{'status':'complete','rows':rows,'seconds':time.monotonic()-start,'inputs_unchanged':True,'os':native[-1]['os']})
      cards=[]
      for index,image in enumerate(records):
        row=rows[index*2];requests=row.get('requests',{})
        labels=requests.get('classification',{}).get('observations',[])[:5]
        summary=', '.join(x['identifier'] for x in labels)
        cards.append(f'<article><h2>{html.escape(image["id"])} · {image["kind"]}</h2><img src="data:image/jpeg;base64,{image["thumbnail"]}" alt="Local photo"><p>{html.escape(Path(image["path"]).name)}</p><p>Vision labels: {html.escape(summary)}</p><details><summary>1024 / 2048 observations</summary><pre>{html.escape(json.dumps(rows[index*2:index*2+2],indent=2))}</pre></details></article>')
      (a.output/'vision-review.html').write_text('<!doctype html><meta charset="utf-8"><title>Extended Vision diagnostic</title><style>body{font:16px system-ui;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:24px}img{width:100%;height:350px;object-fit:contain}pre{white-space:pre-wrap}</style><h1>Extended Vision diagnostic</h1><p>Classification labels and face/subject observations are diagnostic, not interest or culling verdicts. Existing grouping is preserved.</p><main>'+''.join(cards)+'</main>')
      save('manifest.json',{'status':'complete','images':records,'baseline':str(a.baseline),'solos':str(a.solos),'helper_sha256':digest(a.helper)})
    except BaseException as exc:
      save('vision-results.json',{'status':'interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed','error':str(exc),'rows':rows,'seconds':time.monotonic()-start});raise
if __name__=='__main__':main()
