"""Build a private static review report from completed/checkpointed local outputs."""
from __future__ import annotations
import argparse, base64, collections, html, json, statistics
from pathlib import Path

def esc(value):return html.escape(str(value),quote=True)
def summary(result):
    runs=[r for r in result['runs'] if r.get('assessments')];output={}
    kinds={r['id']:r['kind'] for r in result['images']}
    for condition in ('general-solo','scene-solo'):
        for kind in ('grouped','solo'):
            rows=[a for r in runs if r['condition']==condition for a in r['assessments'] if kinds[a['id']]==kind]
            output[condition+'/'+kind]={'n':len(rows),'interest':dict(collections.Counter(r['interest'] for r in rows)),'problems':dict(collections.Counter(r['problem_review'] for r in rows)),'scenes':dict(collections.Counter(r['primary_scene'] for r in rows))}
    general={a['id']:a for r in runs if r['condition']=='general-solo' for a in r['assessments']}
    scene={a['id']:a for r in runs if r['condition']=='scene-solo' for a in r['assessments']}
    shared=general.keys() & scene.keys()
    output['general_vs_scene']={'n':len(shared),'interest_changes':sum(general[i]['interest']!=scene[i]['interest'] for i in shared),'problem_changes':sum(general[i]['problem_review']!=scene[i]['problem_review'] for i in shared),'scene_changes':sum(general[i]['primary_scene']!=scene[i]['primary_scene'] for i in shared)}
    output['performance']={'calls_with_assessments':len(runs),'failed_calls':sum(r.get('status')=='failed' for r in result['runs']),'median_seconds':statistics.median([r['seconds'] for r in runs]) if runs else None,'total_seconds':result['seconds'],'peak_child_rss_bytes':result['peak_child_rss_bytes'],'note':'Child RSS excludes model daemon/unified-memory allocation; human agreement awaits new labels.'}
    output['context_changes']=[]
    for r in runs:
        if '-group-' not in r['condition'] and r['condition']!='general-six-image-group':continue
        independent=scene if r['condition'].startswith('scene-') else general
        for a in r['assessments']:
            if a['id'] in independent and a['interest']!=independent[a['id']]['interest']:
                output['context_changes'].append({'id':a['id'],'condition':r['condition'],'independent':independent[a['id']]['interest'],'grouped':a['interest']})
    return output

def render(result,vision,human_labels=None):
    observations={(r['id'],r['max_dimension']):r for r in vision['rows'] if r['status']=='ok'}
    cards=[]
    images=sorted(result['images'],key=lambda r:(r['group'] is None,r['group'] or '',r['id']))
    for image in images:
        relevant=[(r,a) for r in result['runs'] for a in r.get('assessments',[]) if a['id']==image['id']]
        models=[]
        for run,a in relevant:
            ordering=''
            if run.get('assessment_order_semantics')=='editing_priority' and len(run.get('assessments',[]))>1:
                position=next(i for i,item in enumerate(run['assessments'],1) if item['id']==image['id'])
                ordering='<br>Editing review order: '+str(position)+' / '+str(len(run['assessments']))+' (within this comparison)'
            models.append(f'<tr><td>{esc(run["condition"])}{ordering}</td><td>{esc(a["interest"])}<br>{esc(a["interest_reason"])}</td><td>{esc(a["problem_review"])}<br>{esc(a["problem_reason"])}</td><td>{esc(a["primary_scene"])}<br>{esc(", ".join(a["secondary_tags"]))}</td><td>{esc(a["uncertainty"])}</td></tr>')
        # Previews are reused from checksum-verified historical records; exact model PNGs remain beside results.
        for run in result['runs']:
            if run.get('status')=='failed' and image['id'] in run.get('ids',[]):models.append('<tr><td>'+esc(run['condition'])+'</td><td colspan="4">Failed assessment: '+esc(run.get('error','unknown failure'))+'</td></tr>')
        preview=image.get('thumbnail','')
        frame=observations.get((image['id'],1024),{});requests=frame.get('requests',{})
        labels=requests.get('classification',{}).get('observations',[])[:5]
        label_text=', '.join(r['identifier'] for r in labels)
        boxes=''
        for name,color in [('face_quality','#ff8b38'),('people','#55d2ed'),('animals','#94db5a'),('attention','#e869f1'),('objectness','#e4ce52')]:
            for o in requests.get(name,{}).get('observations',[]):
                if 'box' not in o:continue
                x,y,w,h=o['box'];boxes+=f'<rect x="{x*100}" y="{y*100}" width="{w*100}" height="{h*100}" fill="none" stroke="{color}" stroke-width=".4"><title>{esc(name)}</title></rect>'
        face_quality=[r.get('quality') for r in requests.get('face_quality',{}).get('observations',[])]
        technical='<p>Focus review suggested: '+esc('; '.join(image['focus_review'].get('reason',[])))+'</p>' if image.get('focus_review',{} ) and image['focus_review'].get('review_suggestion') else ''
        history=''
        if human_labels and image.get('group'):
            old=human_labels.get('answers',{}).get(image['group'],{})
            choice=old.get('blind_choice',old.get('choice'))
            wording='No clear favorite recorded' if choice=='none' else ('Previously selected favorite' if choice==image['baseline_index'] else 'Another image was previously selected; this does not mean this image is unacceptable')
            if choice is not None:history='<details><summary>Historical human preference, separate from this trial</summary><p>'+esc(wording)+'</p><p>'+esc(old.get('notes',''))+'</p></details>'
        independent=next((a['interest'] for r,a in relevant if r['condition']=='general-solo'),'unassessed')
        scene_options=''.join('<option value="'+s+'">'+esc(s.replace('_',' ').title())+'</option>' for s in ['portrait','group_portrait','landscape','urban','architecture','wildlife','action','still_life','macro','documentary','other_uncertain'])
        cards.append(f'''<article data-id="{esc(image['id'])}" data-kind="{image['kind']}" data-interest="{independent}"><h2>{esc(image['group'] or 'Solo')} · {esc(image['id'])}</h2><p>{esc(Path(image['path']).name)}</p><div class="picture"><img src="data:image/jpeg;base64,{preview}" alt="Local photograph {esc(image['id'])}"><svg class="overlays" viewBox="0 0 100 100" preserveAspectRatio="none">{boxes}</svg></div>
        <div class="human"><label>Interesting to edit <select name="interest"><option value="">Unjudged</option><option>interesting</option><option>maybe</option><option>no_clear_interest</option><option>uncertain</option></select></label> <label>Worth keeping <select name="keep"><option value="">Unjudged</option><option value="yes">Yes</option><option value="no">No</option></select></label> <label>Photographic type <select name="scene"><option value="">Unjudged</option>{scene_options}</select></label><input name="notes" placeholder="Optional notes" aria-label="Notes for {esc(image['id'])}"></div>
        <div class="models"><table><thead><tr><th>Condition</th><th>Interest</th><th>Problem review</th><th>Scene</th><th>Uncertainty</th></tr></thead><tbody>{''.join(models)}</tbody></table>{technical}{history}<details><summary>Vision diagnostic: {esc(label_text)}</summary><p>Face capture quality: {esc(face_quality)}. No face identity verified. Boxes: orange faces, cyan people, green animals, magenta attention, yellow objectness.</p><pre>{esc(json.dumps(frame,indent=2))}</pre></details></div></article>''')
    sections=collections.defaultdict(list)
    for image,card in zip(images,cards):sections[image['group'] or 'Solo images'].append(card)
    grouped_markup=''.join('<section data-kind="'+('solo' if group=='Solo images' else 'grouped')+'"><h2>'+esc(group)+'</h2><div class="cards">'+''.join(group_cards)+'</div></section>' for group,group_cards in sections.items())
    meta=json.dumps({'source_manifest_sha256':result['manifest_sha256'],'model':'system','ids':[r['id'] for r in images]}).replace('<','\\u003c')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Foundation Models pilot review</title><style>body{font:16px system-ui;background:#f4f3ef;margin:24px}header{position:sticky;top:0;background:#f4f3ef;padding:12px;z-index:2}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:24px}article{background:white;padding:18px;border:3px solid transparent}body.revealed article[data-interest=interesting]{border-color:#24774b}.picture{position:relative}img{display:block;width:100%}.overlays{position:absolute;inset:0;width:100%;height:100%;display:none}body.showboxes .overlays{display:block}.models{display:none}body.revealed .models{display:block}table{width:100%;font-size:14px;border-collapse:collapse}td,th{border-bottom:1px solid #ccc;padding:8px;text-align:left;vertical-align:top}pre{white-space:pre-wrap;font-size:12px}input{display:block;width:95%;margin-top:12px}select{margin:8px}article[hidden]{display:none}</style>
        <header><h1>Foundation Models: grouped and solo review</h1><p>Human judgments start with suggestions hidden. Multiple interesting images and ties are valid. Export labels before closing; they are not saved automatically. No action moves, deletes or writes image metadata.</p><label><input style="display:inline;width:auto" type="checkbox" id="reveal"> Reveal model suggestions</label> <label><input style="display:inline;width:auto" type="checkbox" id="boxes"> Show Vision boxes</label> <select id="filter"><option value="all">All images</option><option value="grouped">Grouped images</option><option value="solo">Solo images</option></select><button id="export">Export human labels</button></header><main>'''+grouped_markup+'''</main><script>
        const META='''+meta+''';const answers={};let revealed=false;
        document.querySelector('#reveal').onchange=e=>{revealed=e.target.checked;document.body.classList.toggle('revealed',revealed)};
        document.querySelector('#boxes').onchange=e=>document.body.classList.toggle('showboxes',e.target.checked);
        document.querySelector('#filter').onchange=e=>{document.querySelectorAll('article').forEach(a=>a.hidden=e.target.value!=='all'&&a.dataset.kind!==e.target.value);document.querySelectorAll('section').forEach(a=>a.hidden=e.target.value!=='all'&&a.dataset.kind!==e.target.value)};
        document.querySelectorAll('article').forEach(a=>a.addEventListener('change',()=>{const row={};a.querySelectorAll('select,input').forEach(f=>row[f.name]=f.value);row.cull=row.keep==='yes'?'no':row.keep==='no'?'yes':'';row.model_revealed= revealed;row.vision_overlays_shown=document.querySelector('#boxes').checked===true;answers[a.dataset.id]=row}));
        document.querySelector('#export').onclick=()=>{const b=new Blob([JSON.stringify({...META,answers},null,2)],{type:'application/json'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='foundation-models-human-labels.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
        </script></html>'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--vision',type=Path,required=True);p.add_argument('--supplement',type=Path);p.add_argument('--human-labels',type=Path);a=p.parse_args()
    r=json.loads(a.results.read_text());v=json.loads(a.vision.read_text())
    (a.results.parent/'summary.json').write_text(json.dumps(summary(r),indent=2))
    if a.supplement:
        supplement=json.loads(a.supplement.read_text())
        if supplement['manifest_sha256']!=r['manifest_sha256']:raise ValueError('Supplement source identity mismatch')
        r=dict(r,runs=r['runs']+supplement['runs'])
    human=None
    if a.human_labels:
        human=json.loads(a.human_labels.read_text());manifest=json.loads(Path(r['manifest']).read_text());base=json.loads(Path(manifest['baseline']).read_text())
        if human['experiment_id']!=base['experiment_id']:raise ValueError('Historical human-label identity mismatch')
    tmp=a.results.parent/'review.html.partial';tmp.write_text(render(r,v,human));tmp.replace(a.results.parent/'review.html')
if __name__=='__main__':main()
