"""Audit cached human-face/person boxes against human scene labels and notes."""
from __future__ import annotations
import argparse, collections, html, json, re
from pathlib import Path
from evaluate_human import evaluate

def audit(human,result,vision):
    evaluated=evaluate(human,result);native={(r['id'],r['max_dimension']):r for r in vision['rows'] if r.get('status')=='ok'};images={r['id']:r for r in result['images']};cases=[]
    for case in evaluated['cases']:
        label=case['human'].get('scene','');note=case['human'].get('notes','')
        mention=bool(re.search(r'\b(faces?|heads?|people|person|couple|glasses|sunglasses|mouth)\b',note,re.I))
        if label not in ('portrait','group_portrait') and not mention:continue
        counts={}
        for size in (1024,2048):
            row=native.get((case['id'],size))
            if not row or row['path']!=images[case['id']]['path']:raise ValueError('Missing/mismatched cached detection identity')
            fields={}
            for name in ('face_quality','landmarks','people'):
                request=row['requests'][name];fields[name]=len(request['observations']) if request['status']=='ok' else None
            counts[str(size)]=fields
        cases.append({'id':case['id'],'human_scene':label,'note':note,'counts':counts,'comment_match':mention})
    groups={}
    for label,minimum in [('portrait',1),('group_portrait',2)]:
        rows=[r for r in cases if r['human_scene']==label];groups[label]={'n':len(rows),'required_faces':minimum,'sizes':{}}
        for size in ('1024','2048'):
            valid=[r for r in rows if r['counts'][size]['face_quality'] is not None]
            groups[label]['sizes'][size]={'valid':len(valid),'meets_count':sum(r['counts'][size]['face_quality']>=minimum for r in valid),'below_count':[r['id'] for r in valid if r['counts'][size]['face_quality']<minimum]}
    return {'groups':groups,'cases':cases,'classification':evaluated['conditions'],'limitations':['Face/person counts are detector outputs, not verified visible-person counts or proof of correctly located boxes.','Counts use all returned face-capture-quality observations without a new confidence cutoff.','Human face detectors do not establish dog-face detection.','Comment matches include explicit mentions only; references such as same as previous are not silently expanded.','People out of view expresses absence, not an expected detection.']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--human',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--vision',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):raise ValueError('Private outputs must be outside Git')
    h=json.loads(a.human.read_text());r=json.loads(a.results.read_text());v=json.loads(a.vision.read_text());value=audit(h,r,v)
    a.output.mkdir(exist_ok=False,parents=True);(a.output/'audit.json').write_text(json.dumps(value,indent=2))
    images={i['id']:i for i in r['images']};native={(row['id'],row['max_dimension']):row for row in v['rows'] if row.get('status')=='ok'};cards=[]
    for case in value['cases']:
        image=images[case['id']];row=native[(case['id'],1024)];boxes=''
        for name,color in [('face_quality','#ff8b38'),('people','#31c9e5')]:
            request=row['requests'][name]
            if request['status']!='ok':continue
            for o in request['observations']:
                x,y,w,height=o['box'];boxes+=f'<rect x="{x*100}" y="{y*100}" width="{w*100}" height="{height*100}" fill="none" stroke="{color}" stroke-width=".45"><title>{name}</title></rect>'
        count_text='; '.join(f'{size}: {n["face_quality"]} faces, {n["people"]} people' for size,n in case['counts'].items())
        cards.append(f'<article><h2>{html.escape(case["id"])} · {html.escape(case["human_scene"])}</h2><p>{html.escape(count_text)}</p><p>{html.escape(case["note"])}</p><div class="picture"><img src="data:image/jpeg;base64,{image["thumbnail"]}" alt="Local image"><svg viewBox="0 0 100 100" preserveAspectRatio="none">{boxes}</svg></div></article>')
    (a.output/'review.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Face and person detection audit</title><style>body{font:16px system-ui;margin:24px;background:#f4f3ef}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:24px}article{background:white;padding:18px}.picture{position:relative}img{display:block;width:100%}svg{position:absolute;inset:0;width:100%;height:100%}</style><h1>Face / person box audit</h1><p>Orange: human face boxes. Cyan: person boxes. Overlays show 1024 results; counts include both sizes. A count does not establish that every visible person or face was correctly detected.</p><main>'+''.join(cards)+'</main>')
    print(json.dumps(value['groups'],indent=2))
if __name__=='__main__':main()
