"""Compare exported human judgments with this exact experiment; never infer labels."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any


def evaluate(result: dict[str, Any], labels: dict[str, Any]) -> dict[str, Any]:
    if labels.get('experiment_id') != result['experiment_id']:
        raise ValueError('Evaluation belongs to a different experiment')
    answers=labels.get('answers',{})
    ids={g['id'] for g in result['comparisons']}
    if set(answers)-ids:raise ValueError('Unknown evaluation group')
    totals: dict[str, Any]={'human_judged_groups':0,'no_winner_groups':0,'changed_after_reveal':0,
                          'focus_changes':0,'focus_improved':0,'focus_worsened':0,'categories':{},'gap_cases':[]}
    counts={mode:{'candidate_top1_hits':0,'top2_hits':0,'image_choices':0,'recommendations':0,'recommendation_hits':0} for mode in ('a','b','c')}
    for g in result['comparisons']:
        answer=answers.get(g['id'],{})
        choice=answer.get('blind_choice',answer.get('choice'))
        if choice is None:continue
        if choice!='none' and (isinstance(choice,bool) or not isinstance(choice,int) or choice not in g['members']):raise ValueError('Invalid human choice')
        totals['human_judged_groups']+=1
        totals['changed_after_reveal']+=bool(answer.get('changed_after_reveal'))
        if choice=='none':totals['no_winner_groups']+=1;continue
        category=answer.get('category','unknown')
        cat=totals['categories'].setdefault(category,{'image_choices':0,'a_top1_hits':0,'a_top2_hits':0})
        cat['image_choices']+=1
        for mode in counts:
            ranked=g['ranking_'+mode];c=counts[mode]
            c['image_choices']+=1;c['candidate_top1_hits']+=bool(ranked and ranked[0]==choice);c['top2_hits']+=choice in ranked[:2]
            if g['winner_'+mode] is not None:
                c['recommendations']+=1;c['recommendation_hits']+=g['winner_'+mode]==choice
        a=g['ranking_a'];b=g['ranking_b'];a_hit=bool(a and a[0]==choice);b_hit=bool(b and b[0]==choice)
        cat['a_top1_hits']+=a_hit;cat['a_top2_hits']+=choice in a[:2]
        changed=bool(a and b and a[0]!=b[0])
        totals['focus_changes']+=changed;totals['focus_improved']+=changed and b_hit and not a_hit;totals['focus_worsened']+=changed and a_hit and not b_hit
        totals['gap_cases'].append({'group':g['id'],'gap':g['gap'],'a_top1_agrees':a_hit,'weak_or_chained':g['weak'] or g['chained']})
    for cat in totals['categories'].values():
        cat['a_top1_rate']=cat['a_top1_hits']/cat['image_choices']
        cat['a_top2_rate']=cat['a_top2_hits']/cat['image_choices']
    for c in counts.values():
        n=c['image_choices'];r=c['recommendations']
        c['candidate_top1_rate']=c['candidate_top1_hits']/n if n else None
        c['top2_rate']=c['top2_hits']/n if n else None
        c['recommendation_agreement_rate']=c['recommendation_hits']/r if r else None
    return {**totals,'approaches':counts,'note':'Rates exclude no-winner labels; candidate rates include withheld weak/chained groups. Original blind choices are used when present. Gap cases are descriptive; no validated confidence thresholds.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--evaluations',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    summary=evaluate(json.loads(a.results.read_text()),json.loads(a.evaluations.read_text()))
    with a.output.open('x') as f:json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))
