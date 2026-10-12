"""Candidate region-selection changes; whole-frame rule deliberately unchanged."""
import copy

from subject_review import low_detail,overlap


def contained(inner,outer):
    x,y,w,h=inner;ox,oy,ow,oh=outer
    area=max(0,min(x+w,ox+ow)-max(x,ox))*max(0,min(y+h,oy+oh)-max(y,oy))
    return area/(w*h) if w*h>0 else 0


def high_detail(region):
    value=region.get('smoothed')
    if not region['usable'] or not value or not value['outside']:return False
    ratios=value['region_to_outside']
    return all(ratios.get(k,0)>=1 for k in ('laplacian_variance','tenengrad'))


def revise(decision,small,large):
    result=copy.deepcopy(decision)
    result['baseline_review_suggestion']=decision['review_suggestion']
    result['suppressed_objectness']=[];result['fallback_attention']=[]
    regions=small['focus']['regions'];other=large['focus']['regions']
    faces=[r for r in regions if r['id'].startswith('faces') and high_detail(r)]
    kept=[]
    for cue in result['subject_cues']:
        suppress=False
        if cue['region'].startswith('objectness'):
            for face in faces:
                candidates=[r for r in other if r['id'].startswith('faces')]
                if not candidates:continue
                match=max(candidates,key=lambda r:overlap(face['box'],r['box']))
                if (overlap(face['box'],match['box'])>=.5 and high_detail(match)
                        and contained(face['box'],cue['box'])>=.8):
                    suppress=True;result['suppressed_objectness'].append({'region':cue['region'],'face':face['id'],
                        'reason':'Overlapping face has higher detail than its context in both metrics at both scales; suppress only the broad objectness cue.'});break
        if not suppress:kept.append(cue)
    # Add attention only when no usable semantic/objectness region exists.
    # This is an uncertain fallback, not semantic recognition of the subject.
    if not any(r['usable'] and not r['id'].startswith('attention') for r in regions):
        for region in regions:
            if not region['id'].startswith('attention') or not low_detail(region):continue
            choices=[r for r in other if r['id'].startswith('attention')]
            if not choices:continue
            match=max(choices,key=lambda r:overlap(region['box'],r['box']))
            if overlap(region['box'],match['box'])>=.5 and low_detail(match):
                result['fallback_attention'].append({'region':region['id'],'box':region['box'],
                    'reason':'Attention-only low-detail fallback; subject identity is unknown and needs manual verification.'})
    result['subject_cues']=kept
    result['review_suggestion']=bool(kept or result['fallback_attention'] or result['global_low_detail'])
    result['category']='manual_review' if result['review_suggestion'] else 'unassessed'
    result['reason']=[c['reason'] for c in kept]+[c['reason'] for c in result['fallback_attention']]
    if result['global_low_detail']:result['reason'].append('Existing whole-frame low-detail trigger retained.')
    if not result['reason']:result['reason']=['No trigger; not certified acceptable focus.']
    return result
