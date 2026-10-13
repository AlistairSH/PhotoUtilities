"""Rerun scores, apply human memberships separately, audit original disagreements."""
from __future__ import annotations
import argparse
import copy
import html
import json
import statistics
import sys
import uuid
from pathlib import Path
from typing import Any
from experiment import digest, rank_groups, render, save, score_rows
from photo_utils.focus import relative_focus


def expanded_result(baseline: dict[str, Any], corrections: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    if baseline['experiment_id'] != corrections['experiment_id']:raise ValueError('Correction experiment mismatch')
    result=copy.deepcopy(baseline)
    groups={f'group-{n:03d}':{**g,'id':f'group-{n:03d}'} for n,g in enumerate(result['groups'],1)}
    affected=set();seen=set()
    for correction in corrections['corrections']:
        i=correction['image_index'];gid=correction['intended_group']
        if gid not in groups or i in seen or i not in result['unmatched']:raise ValueError('Invalid/duplicate membership correction')
        if Path(result['images'][i]['path']).name != correction['filename']:raise ValueError('Correction image mismatch')
        seen.add(i);affected.add(gid);groups[gid]['members'].append(i)
        groups[gid]['members'].sort();groups[gid]['membership_source']='Human-confirmed related set; automatic pair evidence retained unchanged'
    result['groups']=list(groups.values());result['unmatched']=[i for i in result['unmatched'] if i not in seen]
    relative_focus(result,result['focus_rows'])
    result['comparisons']=rank_groups(result)
    return result,affected


def diagnose(result: dict[str, Any], labels: dict[str, Any], affected: set[str]) -> dict[str, Any]:
    if result['experiment_id']!=labels['experiment_id']:raise ValueError('Labels experiment mismatch')
    cases=[]
    for g in result['comparisons']:
        answer=labels['answers'].get(g['id'],{});choice=answer.get('blind_choice',answer.get('choice'))
        if choice is None:continue
        ranked=g['ranking_a'];top=ranked[0];image=result['images'][top]
        human=result['images'][choice] if choice!='none' else None
        def info(im: dict[str, Any]) -> dict[str, Any]:
            return {'filename':Path(im['path']).name,'score':im['aesthetics']['overallScore'],
                    'orientation':im['aesthetics']['orientation'],'utility':im['aesthetics']['isUtility'],
                    'focus_flag':im.get('focus_review',{}).get('review_suggestion'),
                    'focus_comparison':im.get('focus_comparison'),
                    'semantic_counts':{k:len(im.get('detectors',{}).get(k,{}).get('regions',[])) for k in ('faces','people','animals')}}
        pair=next((p for p in g['direct_pairs'] if choice!='none' and {p['a'],p['b']}=={choice,top}),None)
        cases.append({'group':g['id'],'members':len(g['members']),'requires_expanded_review':g['id'] in affected,
             'human_index':choice,'human':info(human) if human else None,'apple_index':top,'apple':info(image),
             'human_rank':ranked.index(choice)+1 if human else None,'agrees':choice==top if human else None,
             'top2_agrees':choice in ranked[:2] if human else None,'score_deficit':image['aesthetics']['overallScore']-human['aesthetics']['overallScore'] if human else None,
             'gap':g['gap'],'recommendation_withheld':g['winner_a'] is None,'human_apple_direct_pair':pair,
             'category':answer.get('category','unknown'),'human_note':answer.get('notes','')})
    choices=[c for c in cases if c['human']]
    larger=[c for c in choices if c['members']>2];pairs=[c for c in choices if c['members']==2]
    matches=[c['gap'] for c in choices if c['agrees']];misses=[c['gap'] for c in choices if not c['agrees']]
    return {'cases':cases,'image_choices':len(choices),'top1_hits':sum(c['agrees'] for c in choices),
        'top2_hits':sum(c['top2_agrees'] for c in choices),
        'pair_groups':len(pairs),'pair_top1_hits':sum(c['agrees'] for c in pairs),
        'larger_groups':len(larger),'larger_top1_hits':sum(c['agrees'] for c in larger),'larger_top2_hits':sum(c['top2_agrees'] for c in larger),
        'uniform_random_expected_top1':sum(1/c['members'] for c in choices)/len(choices) if choices else None,
        'uniform_random_expected_top2':sum(min(2/c['members'],1) for c in choices)/len(choices) if choices else None,
        'median_gap_matches':statistics.median(matches) if matches else None,'median_gap_misses':statistics.median(misses) if misses else None,
        'note':'Supplied reviewed candidate sets only. Random expectations are mathematical reference levels, not tested competing models. Notes describe human reasons, not model explanations.'}


def mismatch_html(baseline: dict[str, Any], diagnostic: dict[str, Any]) -> str:
    esc=html.escape;sections=[]
    for c in diagnostic['cases']:
        if c['agrees'] is True:continue
        cards=[]
        for name,index in [('Your recorded choice',c['human_index']),('Apple raw top',c['apple_index'])]:
            if index=='none':cards.append('<article><h3>Your choice: No clear winner</h3></article>');continue
            image=baseline['images'][index];score=image['aesthetics']
            cards.append(f'<article><h3>{name}</h3><a href="{esc(Path(image["path"]).as_uri(),quote=True)}"><img src="data:image/jpeg;base64,{score["preview"]}"></a><p>{esc(Path(image["path"]).name)} · score {score["overallScore"]:.6f}</p><p>Focus review trigger: {bool(image["focus_review"]["review_suggestion"])}</p></article>')
        sections.append(f'<section><h2>{c["group"]}</h2><p>Your note: {esc(c["human_note"]) or "None supplied"}</p><p>Your image rank: {c["human_rank"] or "No winner"}; top-two gap: {c["gap"]:.6f}. {"Expanded membership awaiting fresh selection." if c["requires_expanded_review"] else "Reviewed candidate membership."}</p><div class="cards">{"".join(cards)}</div></section>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Human versus Apple mismatch audit</title><style>body{font:16px system-ui;margin:24px;background:#f4f3ef}section{background:white;padding:20px;margin:24px 0}.cards{display:flex;flex-wrap:wrap;gap:20px}article{flex:1 1 400px;max-width:700px}img{width:100%;height:480px;object-fit:contain}p{line-height:1.5}</style><h1>Human versus Apple: original choices</h1><p>This is a revealed diagnostic, not a blind test. Your notes explain your preference; Apple exposes no corresponding component explanations. Image pairs are embedded locally. '+esc(diagnostic.get('context','Original sets; expanded groups may still require fresh selection.'))+'</p>'+''.join(sections)+'</html>'


def run(args: argparse.Namespace) -> None:
    baseline=json.loads(args.results.read_text());corrections=json.loads(args.corrections.read_text());labels=json.loads(args.labels.read_text())
    result,affected=expanded_result(baseline,corrections)
    paths=[Path(i['path']) for i in result['images']]
    expected=[i['sha256'] for i in result['images']]
    if [digest(p) for p in paths]!=expected:raise ValueError('Original content changed')
    repo=Path(__file__).resolve().parents[3];out=args.output_dir.resolve()
    if out==repo or repo in out.parents:raise ValueError('Private outputs must stay outside repository')
    out.mkdir(parents=True,exist_ok=False)
    save(out/'run.json',{'status':'running','baseline_experiment':baseline['experiment_id']})
    try:
        scores=score_rows(paths,args.helper,out/'native-errors.txt',out/'scores.partial.json')
        differences=[]
        for i,score in enumerate(scores):
            before=baseline['images'][i]['aesthetics']
            if score['status']!='ok':raise ValueError(f'Native rescore failed for {paths[i]}')
            differences.append({'index':i,'filename':paths[i].name,'delta':score['overallScore']-before['overallScore'],
                                'orientation_same':score['orientation']==before['orientation'],'utility_same':score['isUtility']==before['isUtility']})
            result['images'][i]['aesthetics']=score
        result['comparisons']=rank_groups(result)
        original_id=baseline['experiment_id'];result['baseline_experiment_id']=original_id
        result['experiment_id']=str(uuid.uuid4());result['membership_corrections']=corrections
        result['rerun_score_differences']=differences
        diagnostic=diagnose(baseline,labels,affected)
        if [digest(p) for p in paths]!=expected:raise ValueError('Original content changed during rerun')
        save(out/'results.json',result);save(out/'mismatch-diagnostics.json',diagnostic)
        review=copy.deepcopy(result);review['comparisons']=[g for g in result['comparisons'] if g['id'] in affected];review['unmatched']=[]
        review['groups']=[g for g in result['groups'] if g['id'] in affected]
        save(out/'expanded-review-results.json',review)
        document=render(review).replace('<h1>Blind Apple aesthetics trial</h1>','<h1>Expanded sets: new selections</h1><p>Memberships are supplied by you; automatic direct-pair evidence is unchanged. Choose across the complete sets. Because you have seen some earlier scores, this is a follow-up review rather than a fully independent blind test.</p>')
        (out/'expanded-review.html').write_text(document)
        (out/'mismatch-review.html').write_text(mismatch_html(baseline,diagnostic))
        save(out/'run.json',{'status':'complete','experiment_id':result['experiment_id'],'baseline_experiment':original_id,
             'rescored_images':len(scores),'max_absolute_score_change':max(abs(d['delta']) for d in differences),
             'affected_groups':sorted(affected),'original_checksums_verified':True})
        print(json.dumps({'score_repeat_max_delta':max(abs(d['delta']) for d in differences),'diagnostic_summary':{k:v for k,v in diagnostic.items() if k!='cases'}}))
        for g in review['comparisons']:
            print(g['id'],[(paths[i].name,result['images'][i]['aesthetics']['overallScore']) for i in g['ranking_a']], 'withheld',g['winner_a'] is None)
    except BaseException as exc:
        save(out/'run.json',{'status':'failed','error':str(exc)});raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('results','corrections','labels','helper','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
