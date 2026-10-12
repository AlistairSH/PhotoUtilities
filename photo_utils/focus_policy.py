"""Baseline policy preserved from the reviewed development trials."""
from __future__ import annotations
from typing import Any

VERSION='subject-review-v2'
POLICY: dict[str, Any]={'version':VERSION,'subject_rule':'Laplacian and Tenengrad region/outside ratios below 1 at both 1024 and 2048; matching region IoU >= .5',
        'minimum_region_side':24,'semantic_order':['faces','people','animals','objectness'],
        'attention_role':'Use as uncertain focus region only when no usable face/person/animal/objectness region exists',
        'global_rule':'All six global/strongest-tile signals in the batch bottom 10%, ties counted conservatively',
        'severe_blur_threshold':None,'status':'Unvalidated diagnostic evidence for manual review; no automatic culling'}


def overlap(a: list[float], b: list[float]) -> float:
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    area=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
    total=aw*ah+bw*bh-area
    return area/total if total>0 else 0


def low_detail(region: dict[str, Any]) -> bool:
    measured=region.get('smoothed')
    if not region['usable'] or not measured or not measured['outside']:return False
    ratios=measured['region_to_outside']
    return all(ratios.get(key) is not None and ratios[key]<1 for key in ('laplacian_variance','tenengrad'))


def subject_evidence(small: dict[str, Any], large: dict[str, Any]) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]]=[]
    attention_only=not any(r['usable'] and not r['id'].startswith('attention') for r in small['focus']['regions'])
    for region in small['focus']['regions']:
        kind=region['id'].split()[0]
        if (kind=='attention' and not attention_only) or not low_detail(region):continue
        alternatives=[r for r in large['focus']['regions'] if r['id'].split()[0]==kind]
        if not alternatives:continue
        match=max(alternatives,key=lambda r:overlap(r['box'],region['box']))
        if overlap(match['box'],region['box'])<.5 or not low_detail(match):continue
        cues.append({'region':region['id'],'box':region['box'],'matching_region_2048':match['id'],
                     'ratios_1024':region['smoothed']['region_to_outside'],
                     'ratios_2048':match['smoothed']['region_to_outside'],
                     'reason':(f'{region["id"]} is an uncertain attention-only focus fallback; subject identity is unknown. '
                               if kind=='attention' else '')+f'{region["id"]} has less measured detail than outside pixels in both metrics at both resolutions.'})
    priority={name:i for i,name in enumerate(POLICY['semantic_order'])}
    priority['attention']=len(priority)
    return sorted(cues,key=lambda c:priority[c['region'].split()[0]])


def screen(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths=list(dict.fromkeys(r['path'] for r in rows))
    paired={path:{r['max_dimension']:r for r in rows if r['path']==path} for path in paths}
    signals: list[dict[str, float]]=[]
    for path in paths:
        scales=paired[path]
        if set(scales)!={1024,2048}:raise ValueError('Requires both input resolutions')
        values: dict[str, float]={}
        for scale,row in scales.items():
            global_values=row['focus']['global']['smoothed']
            for metric in ('laplacian_variance','tenengrad'):values[f'{scale}/{metric}']=global_values[metric]
            values[f'{scale}/peak_tile_tenengrad']=max(row['focus']['tile_tenengrad'])
        signals.append(values)
    reference={key:sorted(v[key] for v in signals) for key in signals[0]}
    decisions: list[dict[str, Any]]=[]
    for path,values in zip(paths,signals):
        cues=subject_evidence(paired[path][1024],paired[path][2048])
        fractions={key:sum(v<=values[key] for v in ref)/len(paths) for key,ref in reference.items()}
        global_low=len(paths)>=20 and all(v<=.1 for v in fractions.values())
        reasons=[cue['reason'] for cue in cues]
        if global_low:reasons.append('Low global detail and low strongest-tile detail across both resolutions in this reference batch.')
        contradictory: list[str]=[]
        # Keep contrary regions visible rather than treating a detail ratio as a
        # focus verdict or letting one sharp person clear every other subject.
        for r in paired[path][1024]['focus']['regions']:
            ratio: dict[str, Any]=r['smoothed']['region_to_outside'] if r.get('smoothed') else {}
            if r['id'].split()[0] in ('faces','people','animals') and all(ratio.get(k,0)>=1 for k in ('laplacian_variance','tenengrad')):
                contradictory.append(r['id'])
        decisions.append({'path':path,'review_suggestion':bool(cues) or global_low,'category':'manual_review' if cues or global_low else 'unassessed',
                          'subject_cues':cues,'global_low_detail':global_low,'contrary_regions':contradictory,
                          'reason':reasons or ['No consistent low-detail evidence under this rule; focus is not certified acceptable.'],
                          'global_measurements':values,'global_lower_tail_fractions':fractions,'severe_blur_candidate':False})
    return decisions

