"""Review-only cascade; explicit provisional rules, no changes to photographs."""
import argparse
import copy
import hashlib
import html
import json
from pathlib import Path


def percentile(value, values):
    if value is None or not values:
        return None
    return 100 * (sum(v < value for v in values) + .5 * sum(v == value for v in values)) / len(values)


def detail_selection(detail):
    # Prefer faces, then bodies, then salient regions; never mix kinds in group comparisons.
    for kind in ('faces', 'people', 'animals', 'attention', 'objectness'):
        regions = [r for r in detail['regions'] if r['id'].startswith(kind + ' ') and r['usable'] and r['smoothed'] and r['smoothed']['region']]
        if regions:
            selected = max(regions, key=lambda r: r['smoothed']['region']['pixels'])
            return kind, selected['smoothed']['region']
    return 'global', detail['global']['smoothed']


def apply_scope(rows, reference, solo=False):
    for row in rows:
        reasons = []
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
    def key(r):
        # All suggestions remain in the report. Quality/expression lead before aesthetic tie-breaks.
        return (r['possible_cull'], len(r['reasons']),
                -(r['open_fraction'] if r['open_fraction'] is not None else .5),
                -(r['smile_fraction'] if r['smile_fraction'] is not None else 0),
                -(r['face_quality'] if r['face_quality'] is not None else -1),
                -r['aesthetic'] if use_aesthetic else (r['layout'] if r['layout'] is not None else 1),
                (r['layout'] if r['layout'] is not None else 1) if use_aesthetic else -r['aesthetic'], r['id'])
    return sorted(rows, key=key), use_aesthetic


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):
        raise ValueError('Private outputs must remain outside Git')
    def load(name):
        return json.loads((a.root / name / 'results.json').read_text())
    pilot = load('FoundationModels-20261013-pilot-01')
    details = {r['id']: r for r in load('FoundationModels-20261013-detail-01')['rows']}
    exposure = {r['id']: r for r in load('FoundationModels-20261013-exposure-01')['rows']}
    layouts = {r['id']: r for r in load('FoundationModels-20261013-layout-exposure-01')['rows']}
    vision = json.loads((a.root / 'FoundationModels-20261013-vision-03/vision-results.json').read_text())
    faces = {r['id']: r for r in vision['rows'] if r.get('status') == 'ok' and r['max_dimension'] == 2048}
    native = [json.loads(line) for line in a.native.read_text().splitlines()]
    if len(native) != len(pilot['images']) or any(r['status'] != 'ok' for r in native):
        raise ValueError('Incomplete native analysis')
    rows = []
    for image, n in zip(pilot['images'], native):
        ident = image['id']
        view = a.root / 'FoundationModels-20261013-pilot-01/model-views' / (ident + '-1024.png')
        if Path(n['path']).resolve() != view.resolve() or hashlib.sha256(view.read_bytes()).hexdigest() != details[ident]['view_sha256']:
            raise ValueError('Image/view identity mismatch')
        kind, metric = detail_selection(details[ident]['detail'])
        quality = [o['quality'] for o in faces[ident]['requests']['face_quality']['observations'] if o.get('quality') is not None]
        assessed = [f for f in n['faces'] if f['hasLeftEyePosition'] and f['hasRightEyePosition']]
        anchors = []
        for detector in layouts[ident]['scales']['2048'].values():
            primary = next((o for o in detector['objects'] if o['index'] == detector['primary_index']), None)
            if primary:
                g = primary['geometry']
                anchors.append(min(g['distance_to_center_diagonal_fraction'], g['distance_to_nearest_thirds_diagonal_fraction']))
        exp_regions = [s for s in exposure[ident]['subjects'] if s['status'] == 'ok' and s['kind'] == {'faces': 'face_quality'}.get(kind, kind)]
        clipping_values = [s['clipping'] for s in exp_regions] or [exposure[ident]['global']]
        clip = max(c['near_white_all_channels_percent'] + c['near_black_all_channels_percent'] for c in clipping_values)
        rows.append({'id': ident, 'group': image['group'], 'kind': image['kind'],
                     'utility': n['isUtility'], 'aesthetic': n['overallScore'],
                     'face_quality': max(quality) if quality else None,
                     'detail_kind': kind, 'laplacian': metric['laplacian_variance'], 'tenengrad': metric['tenengrad'],
                     'clipping': clip, 'layout': sum(anchors) / len(anchors) if anchors else None,
                     'assessed_eye_faces': len(assessed), 'expression_face_count': len(n['faces']),
                     'closed_fraction': sum(f['leftEyeClosed'] and f['rightEyeClosed'] for f in assessed) / len(assessed) if assessed else None,
                     'open_fraction': sum(not f['leftEyeClosed'] and not f['rightEyeClosed'] for f in assessed) / len(assessed) if assessed else None,
                     'smile_fraction': sum(f['hasSmile'] for f in n['faces']) / len(n['faces']) if n['faces'] else None})
    for row in rows:
        row['detail_percentile'] = max(percentile(row['laplacian'], [r['laplacian'] for r in rows]), percentile(row['tenengrad'], [r['tenengrad'] for r in rows]))
        row['aesthetic_percentile'] = percentile(row['aesthetic'], [r['aesthetic'] for r in rows])
    sections = []
    for gid in sorted({r['group'] for r in rows if r['group']}):
        members = [r for r in rows if r['group'] == gid]
        ordered, tie = apply_scope(members, members)
        sections.append({'name': gid, 'aesthetic_tiebreak': tie, 'images': ordered})
    global_rows = copy.deepcopy(rows)
    global_order, tie = apply_scope(global_rows, global_rows, solo=True)
    for rank, r in enumerate(global_order, 1):
        r['full_sample_rank'] = rank
    ordered = [r for r in global_order if r['group'] is None]
    for r in ordered:
        r['interesting_candidate'] = not r['possible_cull'] and r['aesthetic_percentile'] >= 90
    sections.append({'name': 'Solo images — full-sample reference', 'aesthetic_tiebreak': tie, 'images': ordered})
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'native.jsonl').write_bytes(a.native.read_bytes())
    policy = ('Provisional review experiment. Utility → low detail → clipping → blink/expression → saliency layout → aesthetic tie-break. No forced drop quota. Group detail requires a same-kind peer ≥1.5× on both Laplacian and Tenengrad. Solo low-detail flags use the bottom 10% of all 93 images; heterogeneous subjects make these less reliable. Clipping needs ≥2% endpoint pixels and ≥2 percentage points excess. Both-eye closure only flags when an open-eye reference exists. Neutral expressions are not culls. Layout flags need a ≥0.10 diagonal-distance gap, using the nearer of center/thirds, averaged across largest attention/objectness boxes; geometry alone is not a composition verdict. Group ordering: flag status/reason count, eyes, smile, highest face quality, then aesthetics when >50% remain, otherwise layout; final tie-break uses the other signal. Missing face scores are shown as unassessed and sort after measured scores. Solos receive a rank among all 93 images using the same cascade order; their flags compare against the full sample rather than their former group. Raw face quality and expression can favor detected portraits over unassessed images. Top-decile aesthetic solos without flags are interesting candidates. No exceptional face-quality cutoff has been selected. Measurements use 1024 display views, face quality/layout use cached 2048 detections. No Foundation Models inference in this report. No files are selected for deletion.')
    (a.output / 'results.json').write_text(json.dumps({'policy': policy, 'reference_images': len(rows), 'sections': sections}, indent=2))
    images = {i['id']: i for i in pilot['images']}
    content = []
    for section in sections:
        cards = []
        for rank, r in enumerate(section['images'], 1):
            image = images[r['id']]
            badge = 'Possible cull' if r['possible_cull'] else ('Interesting candidate' if r.get('interesting_candidate') else 'Review / retain candidate')
            reasons = ''.join('<li>' + html.escape(reason) + '</li>' for reason in r['reasons'])
            global_rank = ('Full-sample rank: ' + str(r['full_sample_rank']) + '/93 · ') if 'full_sample_rank' in r else ''
            quality = 'Unassessed' if r['face_quality'] is None else f'{r["face_quality"]:.3f}'
            cards.append(f'<article class="{"cull" if r["possible_cull"] else "keep"}"><h3>#{rank} · {r["id"]} · {html.escape(Path(image["path"]).name)}</h3><b>{badge}</b><img src="data:image/jpeg;base64,{image["thumbnail"]}" alt="Local sample"><ul>{reasons}</ul><p>{global_rank}Aesthetic {r["aesthetic"]:.3f} · full-sample percentile {r["aesthetic_percentile"]:.1f}<br>Highest face quality: {quality}<br>Detail region: {r["detail_kind"]} · full-sample detail percentile {r["detail_percentile"]:.1f}<br>Endpoint clipping: {r["clipping"]:.2f}% · eye-assessed faces: {r["assessed_eye_faces"]}</p><details><summary>All scoring measurements</summary><pre>{html.escape(json.dumps(r, indent=2))}</pre></details></article>')
        content.append('<section><h2>' + html.escape(section['name']) + '</h2><div class="cards">' + ''.join(cards) + '</div></section>')
    count = sum(r['possible_cull'] for section in sections for r in section['images'])
    (a.output / 'review.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Experimental cascade review</title><style>body{font:16px system-ui;margin:24px;background:#f5f4f0}section{margin:32px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}article{background:white;padding:16px;border-top:6px solid #687e69}.cull{border-color:#bd6625}img{width:100%;margin-top:12px}pre{white-space:pre-wrap}details{margin:14px 0}</style><h1>Experimental cascade review</h1><p>' + str(len(rows)) + ' images · ' + str(count) + ' possible-cull suggestions. Images run best to weakest within each section.</p><details open><summary>Scoring policy and limitations</summary><p>' + html.escape(policy) + '</p></details>' + ''.join(content))
    print(json.dumps({'images': len(rows), 'possible_culls': count, 'solo_interesting': sum(r.get('interesting_candidate', False) for r in ordered), 'report': str(a.output / 'review.html')}))


if __name__ == '__main__':
    main()
