"""Native three-tier selection policy, promoted from the cached review experiment."""
from __future__ import annotations
import copy
import math
from typing import Any, cast
import numpy as np
from numpy.typing import NDArray

VERSION = 'native-three-tier-v1'
TIERS = {'Top Pick': 0, 'Review': 1, 'Possible Cull': 2}
POLICY = ('Experimental selection suggestions; no quotas or automatic deletion. '
          'Groups: utility, same-kind peer >=1.5x on both detail metrics, endpoint clipping '
          '>=2% and >=2 percentage points above reference minimum, or all assessed eyes '
          'closed with an open-eye alternative. Composition is advisory only. '
          'Top Pick requires no technical flags, both full-batch detail percentiles >10, '
          'and face quality >=0.10 above every scored peer or both detail metrics >=1.5x '
          'every same-kind peer. Solos compare against the entire batch; Top Pick requires '
          'top-decile aesthetics and the same detail guard. Missing face quality is '
          'unassessed. No exceptional solo face cutoff. Grain/texture/pose affect scores; '
          'endpoint clipping is measured on display views, not RAW. Personal retention '
          'is a human choice. Existing focus flags remain independent.')

def percentile(value: Any, values: list[Any]) -> Any:
    if value is None or not values:
        return None
    return 100 * (sum(v < value for v in values) + .5 * sum(v == value for v in values)) / len(values)


def detail_selection(detail: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    # Prefer faces, then bodies, then salient regions; never mix kinds in group comparisons.
    for kind in ('faces', 'people', 'animals', 'attention', 'objectness'):
        regions = [r for r in detail['regions'] if r['id'].startswith(kind + ' ') and r['usable'] and r['smoothed'] and r['smoothed']['region']]
        if regions:
            selected = max(regions, key=lambda r: r['smoothed']['region']['pixels'])
            return kind, selected['smoothed']['region']
    return 'global', detail['global']['smoothed']


def apply_scope(rows: list[dict[str, Any]], reference: list[dict[str, Any]], solo: bool = False) -> tuple[list[dict[str, Any]], bool]:
    for row in rows:
        reasons: list[str] = []
        if row['utility']:
            reasons.append('Utility image')
        comparable = [r for r in reference if r['detail_kind'] == row['detail_kind']]
        lap, ten = row['laplacian'], row['tenengrad']
        if solo:
            # Deliberately use the full sample, not a similarity group.
            low_detail = row['detail_percentile'] <= 10
        else:
            low_detail = any(r['laplacian'] >= 1.5 * lap and r['tenengrad'] >= 1.5 * ten
                             for r in comparable if r['id'] != row['id'] and lap > 0 and ten > 0)
        if low_detail:
            reasons.append('Low subject detail' + (' — bottom 10% of full sample' if solo else ' — peer ≥1.5× on both detail metrics'))
        if row['clipping'] >= 2 and row['clipping'] - min(r['clipping'] for r in reference) >= 2:
            reasons.append('More endpoint clipping — ≥2 percentage points above best reference')
        if row['closed_fraction'] == 1 and any(r['open_fraction'] == 1 for r in reference):
            reasons.append('Both eyes reported closed on every assessed face; open-eye alternative available')
        if row['layout'] is not None:
            layouts = [r['layout'] for r in reference if r['layout'] is not None]
            if row['layout'] - min(layouts) >= .10:
                reasons.append('Farther from center/thirds anchors — provisional composition suggestion')
        row['reasons'] = reasons
        row['possible_cull'] = bool(reasons)
    survivors = sum(not r['possible_cull'] for r in rows)
    use_aesthetic = survivors > len(rows) / 2
    def key(r: dict[str, Any]) -> Any:
        # All suggestions remain in the report. Quality/expression lead before aesthetic tie-breaks.
        return (r['possible_cull'], len(r['reasons']),
                -(r['open_fraction'] if r['open_fraction'] is not None else .5),
                -(r['smile_fraction'] if r['smile_fraction'] is not None else 0),
                -(r['face_quality'] if r['face_quality'] is not None else -1),
                -r['aesthetic'] if use_aesthetic else (r['layout'] if r['layout'] is not None else 1),
                (r['layout'] if r['layout'] is not None else 1) if use_aesthetic else -r['aesthetic'], r['id'])
    return sorted(rows, key=key), use_aesthetic

def remove_composition_culls(row: dict[str, Any]) -> None:
    row['composition_advisories'] = [r for r in row['reasons'] if r.startswith('Farther from center/thirds anchors')]
    row['reasons'] = [r for r in row['reasons'] if r not in row['composition_advisories']]
    row['possible_cull'] = bool(row['reasons'])


def assign_tier(row: dict[str, Any], reference: list[dict[str, Any]], solo: bool = False) -> None:
    top_reasons: list[str] = []
    row['top_pick_reasons'] = top_reasons
    if row['possible_cull']:
        row['tier'] = 'Possible Cull'
        return
    # Require both detail measurements outside the bottom decile before promotion.
    # The old detail_percentile is max(two percentiles), so compute each explicitly.
    lap_pct = percentile(row['laplacian'], [r['laplacian'] for r in reference]) if solo else row.get('laplacian_percentile')
    ten_pct = percentile(row['tenengrad'], [r['tenengrad'] for r in reference]) if solo else row.get('tenengrad_percentile')
    if lap_pct is None or ten_pct is None or min(lap_pct, ten_pct) <= 10:
        row['tier'] = 'Review'
        return
    if solo:
        if row['aesthetic_percentile'] >= 90:
            top_reasons.append('Top aesthetic decile across the entire sample, with no technical cull flags')
    else:
        others = [r for r in reference if r['id'] != row['id']]
        qualities = [r['face_quality'] for r in others if r['face_quality'] is not None]
        if row['face_quality'] is not None and qualities and row['face_quality'] - max(qualities) >= .10:
            top_reasons.append('Highest face-capture score ≥0.10 above every other scored group member')
        comparable = [r for r in others if r['detail_kind'] == row['detail_kind']]
        if comparable and all(r['laplacian'] > 0 and r['tenengrad'] > 0 and
                              row['laplacian'] >= 1.5 * r['laplacian'] and
                              row['tenengrad'] >= 1.5 * r['tenengrad'] for r in comparable):
            top_reasons.append('Subject detail ≥1.5× every same-kind peer on both Laplacian and Tenengrad')
    row['tier'] = 'Top Pick' if row['top_pick_reasons'] else 'Review'


def clipping(rgb: NDArray[Any]) -> float:
    return float(cast(Any, 100 * np.mean(np.all(rgb >= 254, axis=2) | np.all(rgb <= 1, axis=2))))


def exposure(rgb: NDArray[Any], detectors: dict[str, Any]) -> dict[str, Any]:
    h, w = rgb.shape[:2]
    subjects: dict[str, list[float]] = {}
    for kind, detection in detectors.items():
        values: list[float] = []
        for region in detection['regions']:
            x, y, bw, bh = region['box']
            pixels = rgb[max(0, math.floor(y*h)):min(h, math.ceil((y+bh)*h)),
                         max(0, math.floor(x*w)):min(w, math.ceil((x+bw)*w))]
            if pixels.size: values.append(clipping(pixels))
        subjects[kind] = values
    return {'global': clipping(rgb), 'subjects': subjects}


def layout(row: dict[str, Any]) -> Any:
    distances: list[float] = []
    for kind in ('attention', 'objectness'):
        regions = row['focus']['regions']
        boxes = [r['box'] for r in regions if r['id'].startswith(kind + ' ')]
        if not boxes: continue
        x, y, w, h = max(boxes, key=lambda b: b[2]*b[3])
        left, top, right, bottom = max(0,x), max(0,y), min(1,x+w), min(1,y+h)
        if right <= left or bottom <= top: continue
        cx, cy = (left+right)/2, (top+bottom)/2
        width, height = row['pixel_size']
        distances.append(min(math.hypot((cx-a)*width, (cy-b)*height)/math.hypot(width,height)
            for a,b in ((.5,.5),(1/3,1/3),(1/3,2/3),(2/3,1/3),(2/3,2/3))))
    return sum(distances)/len(distances) if distances else None


def rank(result: dict[str, Any], focus_rows: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    by_path = {(r['path'],r['max_dimension']):r for r in focus_rows}
    for index, image in enumerate(result['images']):
        small, large = by_path[(image['path'],1024)], by_path[(image['path'],2048)]
        native = image['ranking_native']
        if native.get('status') != 'ok': raise ValueError('Incomplete native ranking evidence')
        kind, metric = detail_selection(small['focus'])
        assessed = [f for f in native['faces'] if f['hasLeftEyePosition'] and f['hasRightEyePosition']]
        qualities = large['ranking_native']['face_qualities']
        clip = small['exposure']['subjects'].get(kind) or [small['exposure']['global']]
        rows.append(dict(id=index, utility=native['isUtility'], aesthetic=native['overallScore'],
            face_quality=max(qualities) if qualities else None, detail_kind=kind,
            laplacian=metric['laplacian_variance'], tenengrad=metric['tenengrad'],
            clipping=max(clip), layout=layout(large),
            closed_fraction=sum(f['leftEyeClosed'] and f['rightEyeClosed'] for f in assessed)/len(assessed) if assessed else None,
            open_fraction=sum(not f['leftEyeClosed'] and not f['rightEyeClosed'] for f in assessed)/len(assessed) if assessed else None,
            smile_fraction=sum(f['hasSmile'] for f in native['faces'])/len(native['faces']) if native['faces'] else None))
    for r in rows:
        for metric in ('laplacian','tenengrad','aesthetic'):
            r[metric+'_percentile'] = percentile(r[metric],[x[metric] for x in rows])
        r['detail_percentile'] = max(r['laplacian_percentile'],r['tenengrad_percentile'])
    for group in result['groups']:
        members: list[dict[str, Any]] = [rows[int(i)] for i in group['members']]
        ordered,_ = apply_scope(members,members)
        for r in ordered:
            remove_composition_culls(r); assign_tier(r,members)
        ordered.sort(key=lambda r: TIERS[r['tier']])
        group['members'] = [r['id'] for r in ordered]
    all_rows = copy.deepcopy(rows)
    ordered,_ = apply_scope(all_rows,all_rows,solo=True)
    for r in ordered:
        remove_composition_culls(r); assign_tier(r,all_rows,solo=True)
    ordered.sort(key=lambda r: TIERS[r['tier']])
    unmatched = set(result['unmatched'])
    for position,r in enumerate(ordered,1):
        if r['id'] in unmatched:
            r['full_sample_rank'] = position
            rows[r['id']] = r
    result['unmatched'] = [r['id'] for r in ordered if r['id'] in unmatched]
    for image,r in zip(result['images'],rows): image['tier_review'] = r
    result['tier_version'] = VERSION
    result['tier_policy'] = POLICY
    result['tier_reference_images'] = len(rows)
