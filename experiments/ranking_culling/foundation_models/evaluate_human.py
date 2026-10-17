"""Evaluate an explicit human export; comments are data, never file-action commands."""
from __future__ import annotations
import argparse, collections, hashlib, html, json
from pathlib import Path

INTEREST={'interesting','maybe','no_clear_interest','uncertain',''}
SCENES={'portrait','group_portrait','landscape','urban','architecture','wildlife','action','still_life','macro','documentary','other_uncertain',''}

def evaluate(human,result):
    images={i['id']:i for i in result['images']}
    if human.get('source_manifest_sha256')!=result['manifest_sha256']:raise ValueError('Source manifest mismatch')
    ids=human.get('ids',[])
    if len(ids)!=len(set(ids)) or set(ids)!=set(images):raise ValueError('Export image inventory mismatch')
    answers=human.get('answers',{})
    if not isinstance(answers,dict) or set(answers)-set(images):raise ValueError('Unknown human image IDs')
    normalized={}
    for id,row in answers.items():
        if row.get('interest','') not in INTEREST or row.get('keep','') not in {'yes','no',''} or row.get('scene','') not in SCENES:raise ValueError('Invalid human value')
        keep=row.get('keep','');expected='no' if keep=='yes' else 'yes' if keep=='no' else ''
        if row.get('cull','') not in {'',expected}:raise ValueError('Conflicting keep/cull labels')
        normalized[id]=dict(row,cull=expected)
    predictions={}
    for condition in ('general-solo','scene-solo'):
        predictions[condition]={a['id']:a for run in result['runs'] if run['condition']==condition and run['status']=='ok' for a in run['assessments']}
    output={'inventory':len(images),'answer_records':len(answers),'untouched_ids':sorted(set(images)-set(answers)),
        'interest_labels':dict(collections.Counter(r.get('interest','') for r in normalized.values())),
        'keep_labels':dict(collections.Counter(r.get('keep','') for r in normalized.values())),
        'model_revealed_labels':sum(r.get('model_revealed') is True for r in normalized.values()),'conditions':{},'cases':[]}
    for condition,model in predictions.items():
        output['conditions'][condition]={}
        for kind in ('all','grouped','solo'):
            labeled=[id for id,r in normalized.items() if r.get('interest') in {'interesting','maybe','no_clear_interest'} and id in model and (kind=='all' or images[id]['kind']==kind)]
            selected=[id for id in labeled if model[id]['interest']=='interesting'];true=[id for id in labeled if normalized[id]['interest']=='interesting'];hits=set(selected)&set(true)
            keep_labeled=[id for id,r in normalized.items() if r.get('keep') in {'yes','no'} and id in model and (kind=='all' or images[id]['kind']==kind)]
            no=[id for id in keep_labeled if normalized[id]['keep']=='no'];yes=[id for id in keep_labeled if normalized[id]['keep']=='yes']
            scenes=[id for id,r in normalized.items() if r.get('scene') and id in model and (kind=='all' or images[id]['kind']==kind)]
            output['conditions'][condition][kind]={'interest_judged':len(labeled),'human_interesting':len(true),'model_interesting':len(selected),'highlight_hits':len(hits),
                'highlight_precision':len(hits)/len(selected) if selected else None,'highlight_recall':len(hits)/len(true) if true else None,
                'model_highlighted_maybes':sum(normalized[id]['interest']=='maybe' for id in selected),
                'model_highlighted_no_clear_interest':sum(normalized[id]['interest']=='no_clear_interest' for id in selected),
                'keep_judged':len(keep_labeled),'human_keep':len(yes),'human_cull':len(no),
                'model_highlighted_human_cull':sum(model[id]['interest']=='interesting' for id in no),
                'model_problem_flags_on_human_cull':sum(model[id]['problem_review']=='possible_problem' for id in no),
                'model_problem_flags_on_human_keep':sum(model[id]['problem_review']=='possible_problem' for id in yes),
                'scene_judged':len(scenes),'scene_exact_matches':sum(model[id]['primary_scene']==normalized[id]['scene'] for id in scenes)}
    for id,row in normalized.items():
        output['cases'].append({'id':id,'kind':images[id]['kind'],'group':images[id]['group'],'human':row,
            'models':{c:m.get(id) for c,m in predictions.items()}})
    output['limitations']=['Blank interest is unjudged even when keep is no or a note describes poor quality.',
        'Keep no combines redundancy, preference and technical concerns; it is not a technical-defect label.',
        'Reported hidden suggestions do not erase prior exposure to earlier experiments.',
        'Scene exact-match counts measure supplied primary labels only; multiple scene/context labels may be valid.',
        'No automatic archive action, personalized training or causal claim about model reasoning follows from this export.']
    return output

def main():
    p=argparse.ArgumentParser();p.add_argument('--human',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    repo=Path(__file__).resolve().parents[3]
    if a.output.resolve().is_relative_to(repo):raise ValueError('Private labels/reports must remain outside Git')
    raw=a.human.read_bytes();human=json.loads(raw);result=json.loads(a.results.read_text());value=evaluate(human,result)
    a.output.mkdir(exist_ok=False,parents=True);(a.output/'human-labels-original.json').write_bytes(raw)
    value['human_sha256']=hashlib.sha256(raw).hexdigest();value['model_results_sha256']=hashlib.sha256(a.results.read_bytes()).hexdigest()
    (a.output/'evaluation.json').write_text(json.dumps(value,indent=2))
    general=value['conditions']['general-solo']['all'];scene=value['conditions']['scene-solo']['all']
    text=f'''# Human review evaluation

The labels distinguish editing interest from personal retention. Family/friend snapshots may be worth keeping for memories without being editing candidates. Blank fields remain unjudged; notes are preserved verbatim and never treated as deletion instructions.

{value['answer_records']} answer records cover an inventory of {value['inventory']} images. Explicit interest judgments: {general['interest_judged']}; interesting: {general['human_interesting']}. Keep decisions: {general['keep_judged']}; keep: {general['human_keep']}; possible cull by the inverse keep rule: {general['human_cull']}.

General prompts highlighted all {general['model_interesting']} explicitly interest-judged images. Only {general['highlight_hits']} match human interesting labels: precision {general['highlight_precision']:.1%}. The other highlights include {general['model_highlighted_maybes']} maybes and {general['model_highlighted_no_clear_interest']} images labeled no clear interest. Recall is {general['highlight_recall']:.1%}, which follows from selecting everything and offers no workload reduction. Scene-aware prompts have the same {scene['highlight_precision']:.1%} precision on explicitly interest-judged images.

Both individual model conditions flagged zero of the {general['human_cull']} human cull choices as possible problems. This includes preference/redundancy decisions and must not be presented as technical-problem recall. Blank keep/interest decisions remain unjudged, even when a note describes poor quality.

## Explanation review

The companion comparison.html preserves each human comment alongside both model explanations. Review whether a reason identifies a concrete editing opportunity or simply describes recognizable content, color, mood, texture or clutter positively. Explanations are not evidence of accurate internal reasoning.

## Revised experimental direction

- Define Interesting as a compelling editing or restoration candidate, not merely a recognizable scene, pleasant snapshot or conceivable interpretation.
- Define Maybe as a plausible candidate with a specific uncertainty. Ordinary competent snapshots can be no clear editing interest while still worth keeping.
- Treat personal memory/retention as a human decision; the model cannot know the photograph's private significance.
- Require specific visible reasons for a highlight. Generic 'visual intrigue', mood, texture or narrative alone should not suffice.
- Do not assume technical faults are deliberate. Report obvious/uncertain technical limitations separately, while allowing a compelling imperfect or restoration-worthy image to remain interesting.
- Keep scene labels flexible: people in a wide urban/landscape image need not make it a portrait. Subject/context tags may be more useful than requiring a single exact primary category.
- Use native focus information only as separate evidence, not an automatic editing/cull decision. Conditional comments about keeping the sharper duplicate remain unresolved choices, not commands.

These labels are a development/review set. Freeze the next prompt and strict schema, then assess an independent held-out set before claiming improvement. No new inference or production rule was run as part of this evaluation.
'''
    (a.output/'findings.md').write_text(text)
    cards=[]
    for case in value['cases']:
        note=case['human'].get('notes','');model=case['models']['general-solo'];scene_model=case['models']['scene-solo']
        cells=[case['id'],case['kind'],case['human'].get('interest','') or 'Unjudged',case['human'].get('keep','') or 'Unjudged',note,
               model['interest_reason'] if model else 'Failed/unavailable',scene_model['interest_reason'] if scene_model else 'Failed/unavailable']
        cards.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in cells)+'</tr>')
    (a.output/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>Human versus model triage</title><style>body{font:16px system-ui;margin:24px}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #ddd;vertical-align:top}</style><h1>Human versus Foundation Models</h1><p>Blank labels remain unjudged. Keep is separate from editing interest. No comments cause file actions.</p><table><tr><th>ID</th><th>Set</th><th>Human interest</th><th>Keep</th><th>Human note</th><th>General model reason</th><th>Scene-aware reason</th></tr>'+''.join(cards)+'</table>')
    print(json.dumps({k:v for k,v in value.items() if k!='cases'},indent=2))
if __name__=='__main__':main()
