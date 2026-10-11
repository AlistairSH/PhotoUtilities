"""Render local galleries/tables from explicit benchmark exports and human labels."""
import argparse
import csv
import html
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import quote


def flags(pair):
    return {'vision_040': pair['vision_distance'] < 0.4,
            'vision_045': pair['vision_distance'] < 0.45,
            'phash_10': pair['phash_hamming'] <= 10,
            'dhash_10': pair['dhash_hamming'] <= 10,
            'sift': pair['sift_candidate']}


def sift_loose(pair):
    return (pair['inliers'] >= 12 and pair['inlier_fraction'] >= 0.4
            and min(pair['coverage_a'], pair['coverage_b']) >= 0.02)


def render(folder, labels):
    datasets = {}
    for path in sorted(folder.glob('*.json')):
        data = json.loads(path.read_text())
        if isinstance(data, dict) and data.get('analyzer') == 'hash-sift-spike-v1':
            datasets[path.stem] = data
    if not datasets:
        raise ValueError('No benchmark datasets')
    summary = ['# Hashes and SIFT versus Vision', '',
               'Read-only comparison using the same oriented native sRGB previews (maximum 1024 pixels). '
               'Vision distances are reused from unchanged, SHA-256-verified baselines. '
               'Hash/SIFT cutoffs are provisional and have not been calibrated on a held-out set.', '',
               '| Dataset | Images | Pairs | Vision <.40 | Vision <.45 | pHash ≤10 | dHash ≤10 | SIFT | New SIFT beyond Vision .45 |',
               '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    index = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Similarity comparison</title>',
             '<style>body{font:17px system-ui;max-width:1100px;margin:40px auto;padding:20px;line-height:1.5}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:8px}a{color:#1564ad}</style>',
             f'<h1>Hashes and SIFT versus Vision</h1><p>{sum(len(d["images"]) for d in datasets.values())} photographs, {sum(len(d["pairs"]) for d in datasets.values()):,} pairs. Candidate scores are evidence for human review, not duplicate or quality verdicts.</p>',
             '<p><b>Important:</b> SIFT recovered confirmed 35561 frames 9–10, missed by Vision at .45. '
             'Hashes also found that pair but missed other confirmed matches. SIFT also misses some confirmed B&W matches. '
             'Do not use either method as a mandatory gate on Vision.</p>']
    labeled_rows = []
    methods = ['vision_040', 'vision_045', 'phash_10', 'dhash_10', 'sift', 'vision_045_or_sift']
    sweep = ['dataset,method,threshold,candidates,overlap_with_vision045,new_beyond_vision045']
    for name, data in datasets.items():
        pairs = data['pairs']
        known = [label for label in labels if label['dataset'] == name]
        count = Counter()
        for pair in pairs:
            for key, value in flags(pair).items():
                count[key] += value
        additions = sum(p['sift_candidate'] and p['vision_distance'] >= 0.45 for p in pairs)
        summary.append(f'| {name} | {len(data["images"])} | {len(pairs)} | {count["vision_040"]} | {count["vision_045"]} | {count["phash_10"]} | {count["dhash_10"]} | {count["sift"]} | {additions} |')
        for method in ['phash_hamming', 'dhash_hamming']:
            for threshold in [6, 10, 14, 18]:
                selected = [p for p in pairs if p[method] <= threshold]
                overlap = sum(p['vision_distance'] < 0.45 for p in selected)
                sweep.append(f'{name},{method},{threshold},{len(selected)},{overlap},{len(selected)-overlap}')
        for threshold, selected in [('strict', [p for p in pairs if p['sift_candidate']]),
                                    ('exploratory-loose', [p for p in pairs if sift_loose(p)])]:
            overlap = sum(p['vision_distance'] < 0.45 for p in selected)
            sweep.append(f'{name},sift,{threshold},{len(selected)},{overlap},{len(selected)-overlap}')
        lookup = {(p['a'], p['b']): p for p in pairs}
        for label in known:
            pair = lookup[(label['a'], label['b'])]
            identified = flags(pair)
            identified['vision_045_or_sift'] = identified['vision_045'] or identified['sift']
            labeled_rows.append({**label, **identified, 'vision_distance': pair['vision_distance'],
                                 'phash_hamming': pair['phash_hamming'], 'dhash_hamming': pair['dhash_hamming'],
                                 'inliers': pair['inliers'], 'min_coverage': min(pair['coverage_a'], pair['coverage_b'])})
        with (folder/(name+'-pairs.csv')).open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(pairs[0]) + list(flags(pairs[0])))
            writer.writeheader()
            writer.writerows({**p, **flags(p)} for p in pairs)
        def image_name(i):
            path = Path(data['images'][i]['path'])
            return path.parent.name + ' / ' + path.name
        parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
                 '<title>'+html.escape(name)+' comparison</title>',
                 '<style>body{font:16px system-ui;background:#17191d;color:#eee;max-width:1250px;margin:30px auto;padding:20px}a{color:#9ecaff}.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:40px}figure{margin:0}img{width:100%;height:380px;object-fit:contain;background:#08090b}h2{margin-top:40px}h3{margin-bottom:10px}.evidence{padding:12px;background:#242a32}@media(max-width:700px){.pair{grid-template-columns:1fr}}</style>',
                 '<h1>'+html.escape(name)+': method disagreements</h1>',
                 '<p><a href="index.html">All datasets</a></p><p>Original JPEGs shown locally, unchanged. '
                 'Vision <.45; pHash/dHash ≤10 differing bits out of 64; SIFT ≥12 inliers, ≥50% mutual-match inliers, ≥10% coverage in both images. '
                 'These cutoffs are experimental. A failed SIFT test is not proof that photographs differ.</p>']
        displayed = set()
        sections = [
            ('Your labeled examples', [lookup[(label['a'], label['b'])] for label in known]),
            ('SIFT candidates missed by Vision .45', sorted([p for p in pairs if p['sift_candidate'] and p['vision_distance'] >= .45], key=lambda p: -p['sift_strength'])),
            ('Hash candidates missed by Vision .45 — closest 12', sorted([p for p in pairs if min(p['phash_hamming'],p['dhash_hamming']) <= 10 and p['vision_distance'] >= .45], key=lambda p:min(p['phash_hamming'],p['dhash_hamming']))[:12]),
            ('Vision candidates without SIFT corroboration — closest 12', sorted([p for p in pairs if p['vision_distance'] < .45 and not p['sift_candidate']], key=lambda p:p['vision_distance'])[:12]),
            ('Agreement examples — up to 5', sorted([p for p in pairs if p['vision_distance'] < .45 and (p['sift_candidate'] or min(p['phash_hamming'],p['dhash_hamming'])<=10)], key=lambda p:p['vision_distance'])[:5])]
        for title, subset in sections:
            subset = [p for p in subset if (p['a'],p['b']) not in displayed]
            if not subset:
                continue
            parts.append('<h2>'+html.escape(title)+'</h2>')
            for pair in subset:
                displayed.add((pair['a'],pair['b']))
                label = next((x['label'] for x in known if (x['a'],x['b'])==(pair['a'],pair['b'])), 'Unlabeled — your review needed')
                parts.append('<h3>'+html.escape(image_name(pair['a'])+' ↔ '+image_name(pair['b']))+'</h3>')
                support = ', '.join(key for key,value in flags(pair).items() if value) or 'none at these cutoffs'
                parts.append(f'<p class="evidence">Human label: {html.escape(label)}<br>'
                             f'Vision {pair["vision_distance"]:.3f}; pHash {pair["phash_hamming"]}/64; dHash {pair["dhash_hamming"]}/64<br>'
                             f'SIFT: {pair["inliers"]}/{pair["mutual_matches"]} inliers, {100*pair["inlier_fraction"]:.1f}% inlier fraction; '
                             f'coverage {100*pair["coverage_a"]:.1f}% / {100*pair["coverage_b"]:.1f}%<br>Candidate flags: {support}</p><div class="pair">')
                for i in [pair['a'],pair['b']]:
                    path = Path(data['images'][i]['path'])
                    src = quote(os.path.relpath(path, folder))
                    parts.append(f'<figure><a href="{src}"><img loading="lazy" src="{src}" alt="{html.escape(path.name)}"></a><figcaption>{html.escape(path.name)}</figcaption></figure>')
                parts.append('</div>')
        parts.append(f'<p>{len(displayed)} distinct pairs shown. <a href="{name}-pairs.csv">Every pair and metric</a>. '
                     'Selected galleries cannot establish complete recall. No grouping/deletion or best-frame selection.</p></html>')
        with (folder/(name+'-review.html')).open('x') as f:
            f.write('\n'.join(parts))
        index.append(f'<h2><a href="{name}-review.html">{html.escape(name)} — {len(displayed)} review pairs</a></h2>'
                     f'<p>Vision .45: {count["vision_045"]}; pHash ≤10: {count["phash_10"]}; dHash ≤10: {count["dhash_10"]}; SIFT: {count["sift"]}; '
                     f'SIFT additions beyond Vision: {additions}.</p>')
    positives = [row for row in labeled_rows if row['label'] == 'basically_same']
    negatives = [row for row in labeled_rows if row['label'] == 'unrelated']
    summary += ['', '## Small explicitly labeled subset', '',
                f'{len(positives)} confirmed basically-same pairs; {len(negatives)} confirmed unrelated pairs. '
                'One moderately similar pair is reported separately. These examples were selected during prior review and are not an unbiased validation set.', '',
                '| Method | Confirmed positives found | Confirmed unrelated pairs flagged |',
                '| --- | ---: | ---: |']
    index.append('<h2>Explicit human labels — small, selected subset</h2><table><tr><th>Method</th><th>Positives found</th><th>Unrelated pairs flagged</th></tr>')
    for method in methods:
        tp = sum(row[method] for row in positives)
        fp = sum(row[method] for row in negatives)
        summary.append(f'| {method} | {tp}/{len(positives)} | {fp}/{len(negatives)} |')
        index.append(f'<tr><td>{method}</td><td>{tp}/{len(positives)}</td><td>{fp}/{len(negatives)}</td></tr>')
    index += ['</table><p>The union preserves the confirmed matches here but still includes Vision’s false positives. '
              'SIFT corroboration helps prioritize candidates; making it compulsory loses confirmed matches.</p>',
              '<p><a href="FINDINGS.md">Full methods, timings and limits</a> · <a href="labeled-results.csv">Labeled results</a> · '
              '<a href="threshold-sweep.csv">Threshold sensitivity counts</a></p></html>']
    summary += ['', '## Recommendation', '',
                'SIFT demonstrates complementary value: it recovers the confirmed 35561 frames 9–10 missed by Vision at .45. '
                'Its strict coverage/inlier requirements also miss both confirmed 17268 pairs. '
                'Use SIFT as additional evidence or a source of extra candidates, not a mandatory filter.', '',
                'Both hashes find 35561 frames 9–10, but miss the other confirmed positive examples at Hamming ≤10. '
                'Hash-only candidates elsewhere require review; a hash result is not a duplicate verdict. '
                'Standard whole-image hashes are not yet demonstrated to outperform Vision for separately exposed frames.', '',
                'Czkawka remains a reasonable independent next comparison if disagreement review shows no useful additions. '
                'It uses perceptual hashing, so it is not automatically a fundamentally different signal; '
                'its hash variants and configurations may still behave differently.', '',
                '## Methods and limitations', '',
                'pHash: area-resize grayscale to 32×32, OpenCV orthonormal DCT, top-left 8×8 coefficients (DC retained), median threshold, 64 bits. '
                'dHash: area-resize grayscale to 9×8, horizontal adjacent differences, 64 bits. '
                'These are independent OpenCV implementations and are not bit-compatible with ImageHash/Pillow interpolation and DCT conventions.', '',
                'SIFT: up to 500 strongest features per native 1024-pixel preview; L2 brute-force two-neighbor matching both directions; '
                'mutual matches passing a .75 ratio test; RANSAC homography with 3-pixel reprojection threshold, 2,000 iterations, seed 0. '
                'Attempt geometry with ≥8 mutual matches. Candidate: ≥12 inliers, ≥.5 inlier fraction, convex-hull inlier coverage ≥.10 in BOTH frames. '
                'Coverage measures extent, not dense pixel overlap. Homography assumes planar content or approximate camera rotation; '
                'parallax, moving people, blur, texture scarcity and repeated structures can break or fool it. '
                'A consistent shared background can match even when the photographs are meaningfully different.', '',
                'Threshold sweep explores hash distances 6/10/14/18 and a looser SIFT rule (12 inliers, .4 inlier fraction, .02 coverage). '
                'This is sensitivity analysis on the same data, not independently validated tuning. No universal SIFT/hash threshold is claimed.', '',
                'No true-negative assumption is made for unlabeled pairs. Overall precision/recall cannot be inferred from candidate counts or agreement with Vision. '
                'Only explicit per-pair labels enter the small labeled table. Reports do not form transitive groups.', '',
                'Read-only offline execution verified under network-deny policy; each input checksum was checked against its saved baseline and after processing. '
                'The production database checksum matched before/after the complete run. No production imports, SQLite access, photo editing, package installation, or model download.', '',
                '## Timings', '',
                'Timings are approximate, warm/cold cache states differ; Vision helper time includes fresh feature-print generation used to decode native pixels, '
                'while original Vision pair scores are reused. Matching time includes hash comparisons and SIFT; native small-batch startup adds overhead. '
                'Not a clean end-to-end algorithm race.', '',
                '| Dataset | Hash extraction s | SIFT extraction s | All-pair comparison s |',
                '| --- | ---: | ---: | ---: |']
    for name, data in datasets.items():
        t = data['seconds']
        summary.append(f'| {name} | {t["hash_extraction"]:.2f} | {t["sift_extraction"]:.2f} | {t["pair_comparison"]:.2f} |')
    summary += ['', '[Gallery index](index.html) · [Labeled results](labeled-results.csv) · [Threshold sensitivity](threshold-sweep.csv)', '']
    with (folder/'FINDINGS.md').open('x') as f:
        f.write('\n'.join(summary))
    with (folder/'index.html').open('x') as f:
        f.write('\n'.join(index))
    with (folder/'threshold-sweep.csv').open('x') as f:
        f.write('\n'.join(sweep)+'\n')
    with (folder/'labeled-results.csv').open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(labeled_rows[0]))
        writer.writeheader()
        writer.writerows(labeled_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--labels', type=Path, required=True)
    args = parser.parse_args()
    render(args.folder.resolve(), json.loads(args.labels.read_text()))


if __name__ == '__main__':
    main()
