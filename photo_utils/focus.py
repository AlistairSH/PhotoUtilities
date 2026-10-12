"""Shared focus engine: protected baseline, contrast and scale confirmation."""
from __future__ import annotations
from typing import Any
import cv2
from numpy.typing import NDArray
from .focus_measurements import analyze_regions
from .focus_edges import extract, summarize, flags, SETTINGS
from .focus_policy import screen, overlap, POLICY
from .similarity_native import SimilarityError

VERSION = 'focus-review-g1-contrast-scale-v1'
PARAMETERS: dict[str, Any] = {'baseline':POLICY,'edge':SETTINGS,'scales':[1024,2048],
    'secondary':'global contrast OR objectness contrast when no semantic detection exists',
    'confirmation':'Single-scale global contrast may clear only with supported below-boundary semantic regions at both scales',
    'ranking':'Directly matched photos, comparable subject kind/count/area, both L and T >=1.5x at both scales; heuristic, not calibrated',
    'ranking_ratio':1.5,'status':'Experimental manual-review suggestions; no automatic deletion'}


def measure(rgb: NDArray[Any], detectors: dict[str, Any], path: str, scale: int) -> dict[str, Any]:
    for kind in ('faces','people','animals','objectness','attention'):
        if detectors.get(kind,{}).get('status')!='ok':raise SimilarityError(f'Focus detector unavailable: {kind} for {path}')
        for region in detectors[kind]['regions']:
            box=region['box'];x,y,w,h=map(float,box)
            if w<=0 or h<=0:raise SimilarityError('Invalid focus detection box')
            x0=max(0.,x);y0=max(0.,y);x1=min(1.,x+w);y1=min(1.,y+h)
            region['display_box']=[x0,y0,max(0.,x1-x0),max(0.,y1-y0)]
    focus=analyze_regions(rgb,detectors,'gaussian1')
    edges=extract(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY))
    global_edge=summarize(edges)
    regions=[{'id':f'{kind} {i}','box':r['box'],'metrics':summarize(edges,r['display_box'],rgb.shape[:2])}
             for kind in ('faces','people','animals','objectness','attention') for i,r in enumerate(detectors[kind]['regions'],1)]
    return {'path':path,'max_dimension':scale,'focus':focus,'edge_global':global_edge,
            'edge_flags':flags(global_edge),'edge_regions':regions}


def semantic_subjects(row: dict[str, Any]) -> list[dict[str, Any]]:
    regions=row['edge_regions'];faces=[r for r in regions if r['id'].startswith('faces')]
    result=list(faces)
    for r in regions:
        if r['id'].startswith('animals'):result.append(r)
        if r['id'].startswith('people'):
            x,y,w,h=r['box']
            if not any(x<=f['box'][0]+f['box'][2]/2<=x+w and y<=f['box'][1]+f['box'][3]/2<=y+h for f in faces):result.append(r)
    return result


def decisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base=screen(rows);by_path={p:{r['max_dimension']:r for r in rows if r['path']==p} for p in {r['path'] for r in rows}}
    result: list[dict[str, Any]]=[]
    for d in base:
        scales=list(by_path[d['path']].values());global_flag=any(r['edge_flags']['contrast_proxy'] for r in scales)
        semantic=any(r['id'].split()[0] in ('faces','people','animals') for row in scales for r in row['edge_regions'])
        fallback=not semantic and any(r['id'].startswith('objectness') and r['metrics']['sufficient'] and r['metrics']['contrast_soft_fraction']>=.6 for row in scales for r in row['edge_regions'])
        stable=all(semantic_subjects(row) and all(r['metrics']['sufficient'] and r['metrics']['contrast_soft_fraction']<.6 for r in semantic_subjects(row)) for row in scales)
        # Require spatially corresponding semantic detections across scales.
        a,b=semantic_subjects(scales[0]),semantic_subjects(scales[1])
        stable=stable and len(a)==len(b) and all(any(r['id'].split()[0]==s['id'].split()[0] and overlap(r['box'],s['box'])>=.5 for s in b) for r in a)
        confirmed=not(global_flag and sum(r['edge_flags']['contrast_proxy'] for r in scales)==1 and stable)
        final=d['review_suggestion'] or fallback or (global_flag and confirmed)
        reasons=list(d['reason']) if d['review_suggestion'] else []
        if not d['review_suggestion'] and global_flag and confirmed:reasons.append('Broad edge transitions suggest overall softness.')
        if not d['review_suggestion'] and fallback:reasons.append('Objectness region suggests softness; no semantic subject was detected.')
        result.append({**d,'baseline_review':d['review_suggestion'],'global_contrast_review':global_flag,
            'regional_fallback_review':fallback,'scale_confirmation_cleared':global_flag and not confirmed,
            'review_suggestion':bool(final),'category':'manual_review' if final else 'unassessed',
            'reason':reasons or ['No review flag under this experimental rule; sharpness is not certified.']})
    return result


def relative_focus(result: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    paired={p:{r['max_dimension']:r for r in rows if r['path']==p} for p in {r['path'] for r in rows}}
    def evidence(index: int, scale: int) -> tuple[str,list[dict[str, Any]]]:
        row=paired[result['images'][index]['path']][scale]
        for kind in ('faces','people','animals','objectness','attention'):
            subjects=[r for r in row['focus']['regions'] if r['id'].startswith(kind) and r['usable'] and r.get('smoothed') and r['smoothed'].get('region')]
            if subjects:return kind,subjects
        return 'global',[{'box':[0,0,1,1],'smoothed':{'region':row['focus']['global']['smoothed']}}]
    for group in result['groups']:
        members=set(group['members']);wins: dict[int,list[int]]={i:[] for i in members};losses: dict[int,list[int]]={i:[] for i in members}
        for pair in result['pairs']:
            a,b=pair['a'],pair['b']
            if a not in members or b not in members or pair['level']=='unmatched':continue
            for better,worse in ((a,b),(b,a)):
                convincing=True
                for scale in (1024,2048):
                    ka,ra=evidence(better,scale);kb,rb=evidence(worse,scale)
                    if ka!=kb or len(ra)!=len(rb):convincing=False;break
                    areas_a=sorted(r['box'][2]*r['box'][3] for r in ra);areas_b=sorted(r['box'][2]*r['box'][3] for r in rb)
                    if any(min(x,y)<=0 or max(x,y)>2*min(x,y) for x,y in zip(areas_a,areas_b)):convincing=False;break
                    for metric in ('laplacian_variance','tenengrad'):
                        va=min(r['smoothed']['region'][metric] for r in ra);vb=min(r['smoothed']['region'][metric] for r in rb)
                        if vb<=0 or va<1.5*vb:convincing=False
                if convincing:wins[better].append(worse);losses[worse].append(better)
        for i in members:
            role='sharper' if wins[i] and not losses[i] else 'softer' if losses[i] and not wins[i] else None
            result['images'][i]['focus_comparison']={'role':role,'sharper_than':wins[i],'softer_than':losses[i],'note':'Relative focus candidate within directly matched photos; texture and framing may affect it.'}
