"""Review all images in an explicit focus export, including unmatched originals."""
import argparse
import base64
import csv
import html
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from culling import VERSION, screen
from quality import SETTINGS
from run import digest, implementation_key


def report(exports, records, rules, destination):
    escape = html.escape

    def card(record):
        row = record['image']
        decision = record['decision']
        label = f'{record["batch"]} / {record["relative_path"]}'
        link = escape(quote(os.path.relpath(row['path'], destination.parent)))
        group = f'Group {record["group"]}' if record['group'] is not None else 'Ungrouped'
        details = '<table><tr><th>Measurement</th><th>Value</th><th>Batch lower-tail fraction</th></tr>'
        for key, value in decision['measurements'].items():
            details += f'<tr><td>{escape(key)}</td><td>{value:.5g}</td><td>{decision["lower_tail_fractions"][key]:.1%}</td></tr>'
        details += '</table>'
        return (f'<article id="image-{record["id"]}"><a href="{link}"><img loading="lazy" '
                f'src="data:image/jpeg;base64,{row["thumbnail"]}" alt="{escape(label)}"></a>'
                f'<h3>{escape(label)}</h3><p>{group} · Subject: {escape(decision["subject"])} · '
                f'{"Manual review" if decision["review_shortlist"] else "Unassessed"}</p>'
                f'<p>{escape(decision["reason"])}</p><details><summary>Measurements</summary>{details}'
                '<p>Lower-tail fractions describe this batch’s measurements; they are not blur probabilities.</p>'
                '</details></article>')

    candidates = [r for r in records if r['decision']['review_shortlist']]
    # A small spread of non-selected images helps the user find false negatives.
    controls = []
    for batch in exports:
        others = sorted([r for r in records if r['batch'] == batch and not r['decision']['review_shortlist']],
                        key=lambda r: max(r['decision']['lower_tail_fractions'].values()))
        if others:
            indexes = sorted({round(i*(len(others)-1)/5) for i in range(6)})
            controls.extend(others[i] for i in indexes)
    control_ids = {r['id'] for r in controls}
    candidate_ids = {r['id'] for r in candidates}
    document = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width,initial-scale=1">',
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
                '<title>Experimental blur review</title><style>',
                'body{font:16px system-ui,sans-serif;color:#242a30;background:#f7f6f2;max-width:1400px;margin:auto;padding:24px}',
                '.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}',
                'article{background:white;border:1px solid #cbd0d2;border-radius:8px;padding:12px}',
                'img{width:100%;height:300px;object-fit:contain;background:#e9ebeb}h3{font-size:15px;overflow-wrap:anywhere}',
                'p{line-height:1.5}table{font-size:12px}td,th{padding:4px;text-align:left}summary{cursor:pointer}',
                'a{color:#155b81}h2{margin-top:40px}</style></head><body><h1>Experimental blur review</h1>',
                f'<p>{len(records)} images · {len(candidates)} review suggestions · 0 calibrated severe-blur decisions</p>',
                '<p>This examines grouped and ungrouped photographs. Each batch is screened separately. '
                'Suggestions have low overall detail and low detail even in their strongest measured region at both scales. '
                'Smooth scenes, exposure and photographic materials can produce the same measurements. '
                'Images outside the shortlist may still be blurred. All originals remain unchanged.</p>',
                '<p>Suggestions clustered in one roll or folder can reflect common scan processing, exposure '
                'or scene texture. Do not interpret that concentration as proof that the roll is out of focus.</p>',
                '<p>Label examples in <a href="review.csv">review.csv</a> as acceptable, unintentional_blur, '
                'intentional_softness, low_texture, or uncertain. Include missed blurry photos from the comparison sample '
                'or full collection. Those labels will guide the next experiment.</p>',
                '<p><a href="#shortlist">Review suggestions</a> · <a href="#comparison">Comparison sample</a> · '
                '<a href="#all">Remaining images</a></p>',
                '<details><summary>Provisional screening rule</summary><p>For each batch independently, all six signals '
                '(smoothed global Laplacian, global Tenengrad and strongest-tile Tenengrad at 1024 and 512 pixels) '
                'must fall within the bottom 10%. Ties are included when counting the fraction. '
                'A small sharp region can prevent shortlisting. This is a review-sampling hypothesis, '
                'not an absolute blur threshold or an instruction to discard anything.</p></details>',
                '<details><summary>Suggestions by source folder</summary><table><tr><th>Batch / folder</th><th>Suggested</th><th>Analyzed</th></tr>']
    totals = Counter((r['batch'], str(Path(r['image']['path']).parent)) for r in records)
    selected = Counter((r['batch'], str(Path(r['image']['path']).parent)) for r in candidates)
    for (batch, folder), count in sorted(selected.items()):
        document.append(f'<tr><td>{escape(batch)} / {escape(Path(folder).name)}</td><td>{count}</td><td>{totals[(batch,folder)]}</td></tr>')
    document.extend(['</table></details>', '<h2 id="shortlist">Review suggestions</h2><div class="gallery">',
                ''.join(card(r) for r in candidates) or '<p>No suggestions under this rule.</p>', '</div>',
                '<h2 id="comparison">Comparison sample</h2><p>Six non-shortlisted images per batch spread across '
                'the measured detail range. These are controls for finding missed blur, not approved images.</p><div class="gallery">',
                ''.join(card(r) for r in controls), '</div>',
                '<h2 id="all">Remaining images</h2>'])
    for batch in exports:
        others = [r for r in records if r['batch'] == batch and r['id'] not in candidate_ids | control_ids]
        document.extend([f'<details><summary>{escape(batch)} — {len(others)} remaining images</summary><div class="gallery">',
                         ''.join(card(r) for r in others), '</div></details>'])
    document.append('</body></html>')
    return '\n'.join(document), control_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exports', nargs='+', type=Path, help='Explicit analysis.json exports; each is a separate reference batch')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    exports = {}
    records = []
    batch_rules = {}
    input_hashes = []
    input_paths = []
    seen = set()
    for source in args.exports:
        data = json.loads(source.read_text())
        batch = source.parent.name
        if batch in exports:
            raise ValueError('Batch names must be unique')
        if data['implementation_key'] != implementation_key() or data['settings'] != SETTINGS:
            raise ValueError('Measurement implementation/settings mismatch; rerun focus analysis')
        paths = [Path(p) for p in data['paths']]
        if len(paths) != len(data['images']) or len(paths) != len(data['hashes']):
            raise ValueError('Incomplete analysis export')
        if any(p.is_symlink() for p in paths) or any(p in seen for p in paths):
            raise ValueError('Symlink or overlapping batch inputs are refused')
        if [image['path'] for image in data['images']] != data['paths']:
            raise ValueError('Export image identities mismatch')
        if [digest(p) for p in paths] != data['hashes']:
            raise ValueError('Images changed since focus analysis')
        seen.update(paths)
        input_paths.extend(paths)
        input_hashes.extend(data['hashes'])
        decisions, rules = screen([row['analysis'] for row in data['images']])
        batch_rules[batch] = rules
        exports[batch] = data
        common = Path(os.path.commonpath([str(p.parent) for p in paths]))
        memberships = {i:n for n,g in enumerate(data.get('groups',[]),1) for i in g['members']}
        for i,(image, decision) in enumerate(zip(data['images'], decisions)):
            base64.b64decode(image['thumbnail'], validate=True)
            records.append({'id':len(records)+1, 'batch':batch, 'image':image, 'decision':decision,
                            'sha256':data['hashes'][i], 'relative_path':str(paths[i].relative_to(common)),
                            'group':memberships.get(i)})
    output = args.output_dir.resolve()
    repository = Path(__file__).resolve().parents[2]
    if output == repository or repository in output.parents or any(output == p.parent or p.parent in output.parents for p in input_paths):
        raise ValueError('Output must be outside repository and original image directories')
    document, control_ids = report(exports, records, batch_rules, output/'culling.html')
    if input_hashes != [digest(p) for p in input_paths]:
        raise ValueError('Sources changed during report generation')
    output.mkdir(parents=True, exist_ok=False)
    (output/'culling.html').write_text(document)
    manifest = {'version':VERSION, 'rules_by_batch':batch_rules, 'inputs_unchanged':True,
                'analysis_key':implementation_key(), 'severe_blur_threshold_status':'Not calibrated',
                'images':[{'path':r['image']['path'], 'sha256':r['sha256'], 'batch':r['batch'],
                           'group':r['group'], 'focus':r['image']['analysis'],
                           'comparison_sample':r['id'] in control_ids,
                           **r['decision']} for r in records]}
    (output/'culling-manifest.json').write_text(json.dumps(manifest,indent=2))
    with (output/'review.csv').open('x',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['batch','path','group','review_shortlist','comparison_sample','human_assessment','notes'])
        for r in records:
            writer.writerow([r['batch'],r['image']['path'],r['group'],r['decision']['review_shortlist'],
                             r['id'] in control_ids,'',''])
    print(json.dumps({'images':len(records), 'review_suggestions':sum(r['decision']['review_shortlist'] for r in records),
                      'comparison_images':len(control_ids), 'report':str(output/'culling.html')}))


if __name__ == '__main__':
    main()
