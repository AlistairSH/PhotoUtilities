"""Reduced blind retest: shuffled disagreement pairs with a separate answer key."""
from __future__ import annotations
import argparse
import html
import json
import secrets
import uuid
from pathlib import Path
from typing import Any
from experiment import digest


def prepare(result: dict[str, Any], labels: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if result['experiment_id']!=labels['experiment_id']:raise ValueError('Experiment identity mismatch')
    pairs=[]
    for group in result['comparisons']:
        answer=labels['answers'].get(group['id'],{})
        choice=answer.get('blind_choice',answer.get('choice'))
        if choice is None or choice=='none':continue
        if choice not in group['members']:raise ValueError('Invalid human choice')
        top=group['ranking_a'][0]
        if choice==top:continue
        candidates=[{'index':choice,'origin':'human'},{'index':top,'origin':'apple'}]
        secrets.SystemRandom().shuffle(candidates)
        pairs.append({'source_group':group['id'],'candidates':candidates})
    secrets.SystemRandom().shuffle(pairs)
    identity=str(uuid.uuid4());public={'experiment_id':identity,'version':'blind-reduced-pairs-v1','pairs':[]}
    key={'experiment_id':identity,'baseline_experiment_id':result['experiment_id'],'pairs':{}}
    for n,pair in enumerate(pairs,1):
        pair_id=f'pair-{n:02d}';cards=[];mapping={}
        for letter,candidate in zip(('A','B'),pair['candidates']):
            image=result['images'][candidate['index']]
            cards.append({'slot':letter,'preview':image['aesthetics']['preview']})
            mapping[letter]={'index':candidate['index'],'origin':candidate['origin'],'path':image['path'],'sha256':image['sha256']}
        public['pairs'].append({'id':pair_id,'cards':cards})
        key['pairs'][pair_id]={'source_group':pair['source_group'],'slots':mapping}
    return public,key


def render(public: dict[str, Any]) -> str:
    sections=[]
    for pair in public['pairs']:
        cards=''.join(f'<article><button class="zoom" aria-label="Enlarge image {c["slot"]}"><img src="data:image/jpeg;base64,{c["preview"]}" alt="Candidate {c["slot"]}"></button><label><input type="radio" name="{pair["id"]}" value="{c["slot"]}"> Prefer {c["slot"]}</label></article>' for c in pair['cards'])
        sections.append(f'<section id="{pair["id"]}"><h2>{pair["id"]}</h2><div class="cards">{cards}</div><p><label><input type="radio" name="{pair["id"]}" value="none"> No clear preference</label></p><input class="notes" placeholder="Optional reason" aria-label="Optional reason"></section>')
    metadata=json.dumps({'experiment_id':public['experiment_id'],'version':public['version'],'pairs':[p['id'] for p in public['pairs']]})
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Blind pair comparison</title>
<style>body{font:17px system-ui;background:#f4f3ef;color:#242424;margin:24px}header{background:#f4f3ef;padding:12px;border-bottom:1px solid #aaa}section{background:white;border-radius:12px;padding:20px;margin:24px 0}.cards{display:grid;grid-template-columns:1fr 1fr;gap:20px}.zoom{width:100%;border:0;background:#eee;padding:0;cursor:zoom-in}.zoom img{width:100%;height:500px;object-fit:contain;display:block}label{display:block;padding:12px}input,button{font:inherit}.notes{width:90%;padding:10px}header button{padding:12px}dialog{width:90vw;height:90vh;padding:12px}dialog img{width:100%;height:calc(100% - 60px);object-fit:contain}dialog button{padding:8px}#status{font-weight:600}@media(max-width:700px){.cards{grid-template-columns:1fr}.zoom img{height:360px}}</style>
<header><h1>Blind pair comparison</h1><p>Pick whichever photograph you prefer now. Both the pair sequence and A/B positions have been shuffled. Click a photograph to enlarge it. No identities or scores are revealed here.</p><button id="export">Export choices JSON</button><label>Restore saved choices <input id="import" type="file" accept=".json"></label><p id="status"></p><p id="storage"></p></header>
''' + ''.join(sections) + '''<dialog id="viewer"><button id="close">Close enlarged image</button><img alt="Enlarged candidate"></dialog><script>
const META='''+metadata+''';const KEY='blind-pairs-'+META.experiment_id;let answers={},storageOK=true;
try{answers=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){storageOK=false}
const sections=[...document.querySelectorAll('section')];
function valid(data){if(data.experiment_id!==META.experiment_id)throw Error('This file belongs to another comparison');if(!data.answers||typeof data.answers!=='object')throw Error('Missing answers');for(const [id,a] of Object.entries(data.answers)){if(!META.pairs.includes(id)||!['A','B','none'].includes(a.choice))throw Error('Invalid selection')}return data.answers}
function update(){document.querySelector('#status').textContent=Object.values(answers).filter(a=>a.choice!==undefined).length+' / '+META.pairs.length+' selected';document.querySelector('#storage').textContent=storageOK?'Saved in this browser. Export before closing; the JSON file is your durable copy.':'Browser storage unavailable. Export before closing.'}
function save(){try{localStorage.setItem(KEY,JSON.stringify(answers))}catch(e){storageOK=false}update()}
function apply(){for(const s of sections){const a=answers[s.id]||{};for(const r of s.querySelectorAll('input[type=radio]'))r.checked=r.value===a.choice;s.querySelector('.notes').value=a.notes||''}update()}
for(const s of sections){s.addEventListener('change',()=>{const selected=s.querySelector('input[type=radio]:checked');if(selected)answers[s.id]={...(answers[s.id]||{}),choice:selected.value};save()});s.querySelector('.notes').addEventListener('input',e=>{answers[s.id]={...(answers[s.id]||{}),notes:e.target.value};save()})}
for(const b of document.querySelectorAll('.zoom'))b.onclick=()=>{document.querySelector('#viewer img').src=b.querySelector('img').src;document.querySelector('#viewer').showModal()};document.querySelector('#close').onclick=()=>document.querySelector('#viewer').close();
document.querySelector('#export').onclick=()=>{const complete=Object.fromEntries(Object.entries(answers).filter(([id,a])=>a.choice!==undefined));const blob=new Blob([JSON.stringify({...META,exported_at:new Date().toISOString(),answers:complete},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='blind-pair-evaluations.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
document.querySelector('#import').onchange=async e=>{try{answers=valid(JSON.parse(await e.target.files[0].text()));save();apply()}catch(error){alert(error.message)}};apply();
</script></html>'''


def evaluate(key: dict[str, Any], labels: dict[str, Any]) -> dict[str, Any]:
    if key['experiment_id']!=labels['experiment_id']:raise ValueError('Wrong blind test export')
    counts={'selected':0,'repeated_prior_choice':0,'selected_apple_top':0,'no_clear_preference':0};cases=[]
    for pair_id,answer in labels['answers'].items():
        if pair_id not in key['pairs'] or answer.get('choice') not in ('A','B','none'):raise ValueError('Invalid pair choice')
        choice=answer['choice'];counts['selected']+=1
        if choice=='none':counts['no_clear_preference']+=1;origin=None
        else:
            origin=key['pairs'][pair_id]['slots'][choice]['origin'];counts['repeated_prior_choice' if origin=='human' else 'selected_apple_top']+=1
        cases.append({'pair':pair_id,'group':key['pairs'][pair_id]['source_group'],'choice_origin':origin,'notes':answer.get('notes','')})
    n=counts['selected']-counts['no_clear_preference']
    return {**counts,'total_pairs':len(key['pairs']),'prior_choice_consistency':counts['repeated_prior_choice']/n if n else None,'cases':cases,
            'note':'Reduced candidate sets and prior image exposure limit comparison with the first review; this is a preference-consistency retest.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    result=json.loads(a.results.read_text());labels=json.loads(a.labels.read_text());public,key=prepare(result,labels)
    repo=Path(__file__).resolve().parents[3];out=a.output_dir.resolve()
    if out==repo or repo in out.parents:raise ValueError('Private outputs must remain outside repository')
    for pair in key['pairs'].values():
        for slot in pair['slots'].values():
            if digest(Path(slot['path']))!=slot['sha256']:raise ValueError('Source content changed')
    out.mkdir(parents=True,exist_ok=False)
    with (out/'answer-key.json').open('x') as f:json.dump(key,f,indent=2)
    with (out/'review.html').open('x') as f:f.write(render(public))
    print(f'Created {len(public["pairs"])} randomized pairs: {out / "review.html"}')
