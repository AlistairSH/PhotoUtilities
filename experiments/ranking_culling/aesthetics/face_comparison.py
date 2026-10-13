"""Compare per-face quality with existing human/aesthetic choices; no combined score."""
from __future__ import annotations
import math
from typing import Any


def image_quality(row: dict[str, Any]) -> dict[str, Any]:
    if row['status']!='ok':return {'status':'failed','minimum':None,'mean':None,'count':None}
    faces=row['faces'];values=[f['quality'] for f in faces]
    if not faces:return {'status':'no_face','minimum':None,'mean':None,'count':0}
    if any(v is None for v in values):return {'status':'missing_quality','minimum':None,'mean':None,'count':len(faces)}
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or not 0<=v<=1 for v in values):raise ValueError('Invalid face quality')
    return {'status':'scored','minimum':min(values),'mean':sum(values)/len(values),'count':len(faces)}


def compare(result: dict[str, Any], native: dict[str, Any], labels: dict[str, Any]) -> list[dict[str, Any]]:
    if labels['experiment_id']!=result['experiment_id'] or native['baseline_experiment_id']!=result['experiment_id']:raise ValueError('Experiment identity mismatch')
    rows=native['rows']
    if len(rows)!=len(result['images']):raise ValueError('Missing native rows')
    quality=[]
    for i,(image,row) in enumerate(zip(result['images'],rows)):
        if row['index']!=i or row['path']!=image['path']:raise ValueError('Native identity mismatch')
        quality.append(image_quality(row))
    output=[]
    for group in result['comparisons']:
        members=group['members'];scored=[i for i in members if quality[i]['status']=='scored']
        if not any(quality[i]['count'] for i in members):continue
        ordered=sorted(scored,key=lambda i:(-quality[i]['minimum'],i))
        means=sorted(scored,key=lambda i:(-quality[i]['mean'],i))
        tied=len(ordered)>1 and quality[ordered[0]]['minimum']==quality[ordered[1]]['minimum']
        counts={quality[i]['count'] for i in scored}
        human=labels['answers'].get(group['id'],{});human=human.get('blind_choice',human.get('choice'))
        leader=ordered[0] if len(ordered)>1 and not tied else None
        output.append({'group':group['id'],'members':members,'scored_members':scored,'image_quality':{i:quality[i] for i in members},
              'min_ranking':ordered,'mean_ranking':means,'face_leader':leader,'mean_leader':means[0] if len(means)>1 else None,
              'human':human,'aesthetic_top':group['ranking_a'][0],'complete':len(scored)==len(members),
              'same_detected_count':len(counts)==1,'single_face_complete':len(scored)==len(members) and counts=={1},
              'min_mean_disagree':bool(ordered and means and ordered[0]!=means[0]),'exact_tie':tied,
              'note':'Per-face quality is intended for repeated captures of the same person. Person identity is not verified here. Multi-face minimum/mean are experimental image summaries, not native image scores.'})
    return output
