"""Three-tier review from saved cascade measurements, without new inference."""
import argparse
import copy
import hashlib
import html
import json
from collections import Counter
from pathlib import Path

from cascade_report import apply_scope

TIERS = {'Top Pick': 0, 'Review': 1, 'Possible Cull': 2}
POLICY = (
    'Top Pick: no technical cull flags, both detail metrics above the full-sample '
    'bottom decile, and a clear measured advantage. In groups: highest face-capture '
    'quality at least 0.10 above every other scored peer (at least one peer required), '
    'or both Laplacian and Tenengrad at least 1.5 times every other comparable '
    'same-region-kind peer (at least one required). Compared against all group '
    'members, not just survivors. No promotion merely for being first or for '
    'composition alone. Solos: aesthetic percentile at least 90 against all 93 '
    'sample images; the exceptional face-quality cutoff remains unset. '
    'Review: default for close alternatives, ordinary snapshots, uncertainty and '
    'composition-only concerns. Missing faces are unassessed, not defects; another '
    'measured signal may still support a Top Pick. Possible Cull: existing utility, '
    'substantially lower detail, clipping or detected both-eye closure flags. '
    'Composition remains an ordering hint and advisory, never a cull reason. '
    'No quotas, automatic deletion, new scans or new model inference. '
    'Within each tier retain the prior cascade order. Solos are ranked within '
    'a fresh ordering of all 93 saved measurement rows under full-sample rules, '
    'rather than compared only with other solos. Full-sample percentile comparisons '
    'across different subjects remain experimental. Top Pick means a selection '
    'candidate, not a personal-memory retention decision or a sharpness guarantee.'
)


def remove_composition_culls(row):
    row['composition_advisories'] = [r for r in row['reasons'] if r.startswith('Farther from center/thirds anchors')]
    row['reasons'] = [r for r in row['reasons'] if r not in row['composition_advisories']]
    row['possible_cull'] = bool(row['reasons'])


def assign_tier(row, reference, solo=False):
    row['top_pick_reasons'] = []
    if row['possible_cull']:
        row['tier'] = 'Possible Cull'
        return
    # Require both detail measurements outside the bottom decile before promotion.
    # The old detail_percentile is max(two percentiles), so compute each explicitly.
    from cascade_report import percentile
    lap_pct = percentile(row['laplacian'], [r['laplacian'] for r in reference]) if solo else row.get('laplacian_percentile')
    ten_pct = percentile(row['tenengrad'], [r['tenengrad'] for r in reference]) if solo else row.get('tenengrad_percentile')
    if lap_pct is None or ten_pct is None or min(lap_pct, ten_pct) <= 10:
        row['tier'] = 'Review'
        return
    if solo:
        if row['aesthetic_percentile'] >= 90:
            row['top_pick_reasons'].append('Top aesthetic decile across the entire sample, with no technical cull flags')
    else:
        others = [r for r in reference if r['id'] != row['id']]
        qualities = [r['face_quality'] for r in others if r['face_quality'] is not None]
        if row['face_quality'] is not None and qualities and row['face_quality'] - max(qualities) >= .10:
            row['top_pick_reasons'].append('Highest face-capture score ≥0.10 above every other scored group member')
        comparable = [r for r in others if r['detail_kind'] == row['detail_kind']]
        if comparable and all(r['laplacian'] > 0 and r['tenengrad'] > 0 and
                              row['laplacian'] >= 1.5 * r['laplacian'] and
                              row['tenengrad'] >= 1.5 * r['tenengrad'] for r in comparable):
            row['top_pick_reasons'].append('Subject detail ≥1.5× every same-kind peer on both Laplacian and Tenengrad')
    row['tier'] = 'Top Pick' if row['top_pick_reasons'] else 'Review'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--pilot', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):
        raise ValueError('Private report must remain outside Git')
    source = a.baseline.read_bytes()
    baseline = json.loads(source)
    pilot = json.loads(a.pilot.read_text())
    old = {r['id']: r for s in baseline['sections'] for r in s['images']}
    images = {i['id']: i for i in pilot['images']}
    if len(old) != baseline['reference_images'] or set(old) != set(images):
        raise ValueError('Incomplete or mismatched image identities')
    rows = copy.deepcopy(list(old.values()))
    from cascade_report import percentile
    for r in rows:
        if r['group'] != images[r['id']]['group']:
            raise ValueError('Changed grouping')
        r['laplacian_percentile'] = percentile(r['laplacian'], [x['laplacian'] for x in rows])
        r['tenengrad_percentile'] = percentile(r['tenengrad'], [x['tenengrad'] for x in rows])
        r.pop('interesting_candidate', None)
        remove_composition_culls(r)
    sections = []
    for section in baseline['sections'][:-1]:
        ids = {r['id'] for r in section['images']}
        members = [r for r in rows if r['id'] in ids]
        for r in members:
            assign_tier(r, members)
        members.sort(key=lambda r: TIERS[r['tier']])
        sections.append({'name': section['name'], 'images': members})
    # Recompute only arithmetic ordering from stored metrics; no pixel processing.
    global_rows = copy.deepcopy(rows)
    global_order, _ = apply_scope(global_rows, global_rows, solo=True)
    for r in global_order:
        remove_composition_culls(r)
        assign_tier(r, global_rows, solo=True)
    global_order.sort(key=lambda r: TIERS[r['tier']])
    for rank, r in enumerate(global_order, 1):
        r['full_sample_rank'] = rank
    sections.append({'name': 'Solo images — ranked against all 93 samples',
                     'images': [r for r in global_order if r['group'] is None]})
    new = {r['id']: r for s in sections for r in s['images']}
    counts = dict(Counter(r['tier'] for r in new.values()))
    old_culls = {i for i, r in old.items() if r['possible_cull']}
    new_culls = {i for i, r in new.items() if r['possible_cull']}
    changes = dict(Counter(('Possible Cull' if old[i]['possible_cull'] else 'Review / retain candidate') + ' → ' + r['tier'] for i, r in new.items()))
    audit = {'baseline_images': len(old), 'new_images': len(new), 'counts': counts,
             'transitions': changes, 'old_possible_culls': len(old_culls),
             'new_possible_culls': len(new_culls), 'added_culls': sorted(new_culls - old_culls),
             'removed_culls': sorted(old_culls - new_culls),
             'all_images_preserved': set(new) == set(old),
             'group_memberships_preserved': all(new[i]['group'] == old[i]['group'] for i in old)}
    assert not audit['added_culls']
    assert all(all(reason.startswith('Farther from center/thirds anchors') for reason in old[i]['reasons']) for i in audit['removed_culls'])
    assert counts.get('Top Pick', 0) > 0
    assert changes.get('Review / retain candidate → Review', 0) > changes.get('Review / retain candidate → Top Pick', 0)
    for ident, r in new.items():
        if r['tier'] == 'Top Pick':
            assert not r['possible_cull'] and r['top_pick_reasons']
            assert not old[ident]['possible_cull']
        for field in ('aesthetic', 'face_quality', 'laplacian', 'tenengrad', 'clipping', 'layout'):
            assert r[field] == old[ident][field]
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'results.json').write_text(json.dumps({'policy': POLICY,
        'baseline_sha256': hashlib.sha256(source).hexdigest(), 'reference_images': len(new),
        'sections': sections, 'full_sample_ranking': global_order, 'comparison': audit}, indent=2))
    (a.output / 'comparison.json').write_text(json.dumps(audit, indent=2))
    content = []
    for section in sections:
        cards = []
        for rank, r in enumerate(section['images'], 1):
            image = images[r['id']]
            label = r['tier']
            reasons = r['top_pick_reasons'] + r['reasons'] + r['composition_advisories']
            why = ''.join('<li>' + html.escape(s) + '</li>' for s in reasons)
            face = 'Unassessed' if r['face_quality'] is None else f'{r["face_quality"]:.3f}'
            full_rank = f'Full-sample rank: {r["full_sample_rank"]}/93<br>' if r['group'] is None else ''
            css = {'Top Pick': 'top', 'Review': 'review', 'Possible Cull': 'cull'}[label]
            cards.append(f'<article class="{css}"><h3>#{rank} · {r["id"]} · {html.escape(Path(image["path"]).name)}</h3><b class="badge">{label}</b><img src="data:image/jpeg;base64,{image["thumbnail"]}" alt="Local sample"><ul>{why}</ul><p>{full_rank}Aesthetic: {r["aesthetic"]:.3f} · full-sample percentile {r["aesthetic_percentile"]:.1f}<br>Highest face quality: {face}<br>Detail region: {r["detail_kind"]}<br>Endpoint clipping: {r["clipping"]:.2f}%</p><details><summary>All scoring measurements</summary><pre>{html.escape(json.dumps(r, indent=2))}</pre></details></article>')
        content.append('<section><h2>' + html.escape(section['name']) + '</h2><div class="cards">' + ''.join(cards) + '</div></section>')
    summary = ' · '.join(f'{counts.get(t, 0)} {t}' for t in TIERS)
    audit_text = html.escape(json.dumps(audit, indent=2))
    (a.output / 'review.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Three-tier photo review</title><style>body{font:16px system-ui;margin:24px;background:#f5f4f0;color:#222}section{margin:32px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}article{background:white;padding:16px;border-top:7px solid #8995a1}.top{border-color:#248247}.cull{border-color:#bd6625}.badge{display:inline-block;padding:5px 10px;border-radius:5px;background:#e9edf0}.top .badge{background:#d9efdf}.cull .badge{background:#fae4d5}img{width:100%;margin-top:12px}pre{white-space:pre-wrap}details{margin:14px 0}</style><h1>Three-tier photo review</h1><p>' + summary + '</p><p>Existing measurements only. Top Picks appear first, then Review, then Possible Cull within each section. All 93 images are retained.</p><details><summary>Rules and limitations</summary><p>' + html.escape(POLICY) + '</p><p>Inherited technical rules: utility flag; within-group same-kind peer ≥1.5× on both detail metrics, or solos bottom decile on both full-sample metrics; ≥2% endpoint clipping and ≥2 percentage points above reference minimum; both eyes closed on all assessed faces with an open-eye alternative. All are experimental suggestions. Missing eye positions are unassessed. Face quality includes lighting and pose; grain and texture affect detail. Center/thirds geometry is a coarse composition hint.</p></details><details><summary>Comparison with previous report</summary><pre>' + audit_text + '</pre></details>' + ''.join(content))
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
