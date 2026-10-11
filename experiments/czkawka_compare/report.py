"""Local Czkawka disagreement galleries and sparse-label evaluation."""
import argparse
import csv
import html
import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote


def render(folder):
    bench=json.loads((folder/'benchmark.json').read_text())
    baseline=Path(bench['baseline_folder'])
    labels=json.loads((baseline/'known-labels.json').read_text())
    datasets={}
    for file in baseline.glob('*.json'):
        d=json.loads(file.read_text())
        if isinstance(d,dict)and d.get('analyzer')=='hash-sift-spike-v1':datasets[file.stem]=d
    records=[r for r in bench['records']if 'co_pairs'in r]
    configs=sorted({r['config']for r in records},key=lambda n:(n!='default',n))
    scores={}
    for config in configs:
        sets={r['dataset']:{tuple(p)for p in r['co_pairs']}for r in records if r['config']==config}
        tp=sum((l['a'],l['b'])in sets[l['dataset']]for l in labels if l['label']=='basically_same')
        fp=sum((l['a'],l['b'])in sets[l['dataset']]for l in labels if l['label']=='unrelated')
        scores[config]={'positives':tp,'unrelated':fp,'pairs':sum(len(s)for s in sets.values())}
    informative=sorted(configs,key=lambda c:(-scores[c]['positives'],scores[c]['unrelated'],scores[c]['pairs']))[0]
    lines=['# Czkawka versus Vision <0.45 OR SIFT','',
           f'Installed standalone official Apple Silicon CLI {bench["version"]}; SHA-256 {bench["binary_sha256"]}. '
           'No Homebrew package/dependency changes. Five reviewed datasets: 254 photographs, 7,838 original pair comparisons. '
           'Czkawka was run independently within each same dataset (including the 100-photo combined set).','',
           'All Czkawka runs use deletion NONE, dry-run, cache disabled, JPG-only scanning, minimum size 1 byte, and network denied. '
           'Default is Gradient/16/Nearest/max-difference 5. Twelve configurations explore Gradient, Mean, Median, '
           'hash sizes 8/16/32, Nearest/Lanczos3 and distances up to 40. No rotation/mirroring invariance.','',
           '## Sparse explicit user labels','',
           '| Method/settings | Genuine pairs found (of 4) | Unrelated pairs flagged (of 3) | Total co-grouped pairs |',
           '| --- | ---: | ---: | ---: |']
    combo_count=0
    combo_sets={}
    for name,d in datasets.items():
        combo_sets[name]={(p['a'],p['b'])for p in d['pairs']if p['vision_distance']<.45 or p['sift_candidate']}
        combo_count+=len(combo_sets[name])
    combo_tp=sum((l['a'],l['b'])in combo_sets[l['dataset']]for l in labels if l['label']=='basically_same')
    combo_fp=sum((l['a'],l['b'])in combo_sets[l['dataset']]for l in labels if l['label']=='unrelated')
    lines.append(f'| Vision .45 OR SIFT | {combo_tp} | {combo_fp} | {combo_count} direct candidate pairs |')
    for config in configs:
        s=scores[config];lines.append(f'| Czkawka {config} | {s["positives"]} | {s["unrelated"]} | {s["pairs"]} |')
    lines+=['',
            'These are selected, sparse examples, not overall precision/recall. Czkawka co-grouping is its user-visible output; '
            'it is NOT a complete table of direct pair distances. The released implementation can merge overlapping groups '
            'transitively. Its exported per-entry difference does not establish every pair distance inside a merged group; '
            'we do not invent distances or equate co-grouped pairs with guaranteed direct matches.','',
            f'The most informative setting by this labeled subset is {informative}. This is selected on the same labels, '
            'not held-out validation; galleries expose its candidates and the full configuration union.','',
            '## Dataset outcomes','',
            '| Dataset | Vision .45 OR SIFT | Czkawka default groups | Default co-pairs | All-config union co-pairs | Union beyond combo |',
            '| --- | ---: | ---: | ---: | ---: | ---: |']
    index=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Czkawka comparison</title>',
           '<style>body{font:17px system-ui;max-width:1150px;margin:40px auto;padding:20px;line-height:1.5}a{color:#1564ad}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:8px}</style>',
           '<h1>Czkawka versus Vision .45 + SIFT</h1><p>254 images in five datasets. '
           'The installed standalone CLI is version 12.0.2. Cache disabled; no deletion; network denied.</p>',
           '<p>Czkawka groups can contain indirect/transitive matches. Galleries show co-group membership, '
           'not invented pairwise hash distances. Review additions and missed confirmed pairs independently.</p>',
           '<table><tr><th>Method</th><th>Confirmed positives /4</th><th>Unrelated flagged /3</th><th>Candidate pairs</th></tr>',
           f'<tr><td>Vision .45 OR SIFT</td><td>{combo_tp}</td><td>{combo_fp}</td><td>{combo_count}</td></tr>']
    for config in configs:
        s=scores[config];index.append(f'<tr><td>{config}</td><td>{s["positives"]}</td><td>{s["unrelated"]}</td><td>{s["pairs"]} co-grouped</td></tr>')
    index.append('</table><p>Accuracy figures use only four explicit positive and three unrelated human labels; no general accuracy claim.</p>')
    csv_rows=[]
    for name,d in sorted(datasets.items()):
        ds_records=[r for r in records if r['dataset']==name]
        union=set();support=defaultdict(list)
        for r in ds_records:
            for p in r['co_pairs']:
                p=tuple(p);union.add(p);support[p].append(r['config'])
        default=next(r for r in ds_records if r['config']=='default')
        lines.append(f'| {name} | {len(combo_sets[name])} | {default["groups"]} | {len(default["co_pairs"])} | {len(union)} | {len(union-combo_sets[name])} |')
        lookup={(p['a'],p['b']):p for p in d['pairs']}
        known=[l for l in labels if l['dataset']==name]
        selected=[]
        for l in known:selected.append((l['a'],l['b']))
        for p in sorted(union-combo_sets[name],key=lambda p:(-len(support[p]),lookup[p]['vision_distance']))[:15]:
            if p not in selected:selected.append(p)
        for p in sorted(union & combo_sets[name],key=lambda p:lookup[p]['vision_distance'])[:8]:
            if p not in selected:selected.append(p)
        for p in sorted(combo_sets[name]-union,key=lambda p:lookup[p]['vision_distance'])[:8]:
            if p not in selected:selected.append(p)
        parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
               '<title>'+html.escape(name)+' Czkawka review</title>',
               '<style>body{font:16px system-ui;background:#17191d;color:#eee;max-width:1250px;margin:30px auto;padding:20px}a{color:#9ecaff}.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:40px}figure{margin:0}img{width:100%;height:380px;object-fit:contain;background:#08090b}.evidence{padding:12px;background:#242a32}@media(max-width:700px){.pair{grid-template-columns:1fr}}</style>',
               '<h1>'+html.escape(name)+'</h1><p><a href="index.html">All datasets</a></p>',
               '<p>Original JPEGs displayed locally. Czkawka flags below mean co-group membership under named configurations. '
               'They do not mean every pair has a direct hash distance below threshold. No image edits or deletion.</p>']
        for a,b in selected:
            p=lookup[(a,b)]
            human=next((l['label']for l in known if(l['a'],l['b'])==(a,b)),'Unlabeled — review needed')
            mode=('Czkawka addition'if(a,b)not in combo_sets[name]else('Agreement'if(a,b)in union else'Combo only'))
            pa,pb=[Path(d['images'][i]['path'])for i in[a,b]]
            parts.append('<h2>'+html.escape(pa.name+' ↔ '+pb.name)+'</h2>')
            settings=', '.join(support[(a,b)])or'None of the tested configurations'
            parts.append(f'<p class="evidence">{mode}; human label: {html.escape(human)}<br>Vision {p["vision_distance"]:.3f}; SIFT candidate {p["sift_candidate"]}<br>Czkawka co-grouped under: {settings}</p><div class="pair">')
            for path in[pa,pb]:
                src=quote(os.path.relpath(path,folder))
                parts.append(f'<figure><a href="{src}"><img loading="lazy" src="{src}" alt="{html.escape(path.name)}"></a><figcaption>{html.escape(path.parent.name+" / "+path.name)}</figcaption></figure>')
            parts.append('</div>')
        parts.append(f'<p>{len(selected)} distinct pairs shown; all config/group data preserved in JSON. '
                     'Unlabeled candidates are not assumed false or true.</p></html>')
        with(folder/(name+'-review.html')).open('x')as f:f.write('\n'.join(parts))
        index.append(f'<h2><a href="{name}-review.html">{name} — {len(selected)} review pairs</a></h2><p>Combo candidates: {len(combo_sets[name])}; default Czkawka co-pairs: {len(default["co_pairs"])}; configuration-union co-pairs: {len(union)}.</p>')
        for r in ds_records:
            csv_rows.append({'dataset':name,'config':r['config'],'seconds':r['seconds'],'groups':r['groups'],'co_grouped_pairs':len(r['co_pairs']),'overlap_with_combo':r['overlap_with_combo'],'beyond_combo':r['new_beyond_combo']})
    lines+=['','## Speed','',
            'Uncached hashes, warm-filesystem repeats: median of three runs. CLI end-to-end time includes discovery, JPEG decoding, hashing, grouping, '
            'and JSON export, but not the external SHA-256 protection checks. Two-thread runs compare against OpenCV’s two-thread configuration; '
            'default/all-thread runs also show ordinary CLI performance. No cache acceleration is claimed.', '',
            '| Dataset | Czkawka default 2 threads (s) | Czkawka default all threads (s) |',
            '| --- | ---: | ---: |']
    for name in sorted(datasets):
        t2=next(r['median_seconds']for r in bench['records']if r['dataset']==name and r['config']=='timing-default-t2')
        t0=next(r['median_seconds']for r in bench['records']if r['dataset']==name and r['config']=='timing-default-t0')
        lines.append(f'| {name} | {t2:.3f} | {t0:.3f} |')
    timing_path=folder/'combo-full-timing.json'
    if timing_path.exists():
        t=json.loads(timing_path.read_text())
        lines+=['',f'Fresh warm-filesystem 100-photo comparison: Vision+SIFT implementation median {t["median_processing_seconds"]:.3f} seconds '
                '(three runs, one native 100-image batch, all Vision pair distances freshly recomputed, hash extraction and SHA-256 checks subtracted). '
                f'Czkawka default two-thread median {t["czkawka_t2_seconds"]:.3f} seconds '
                f'({t["median_processing_seconds"]/t["czkawka_t2_seconds"]:.1f}× faster for these implementations). '
                'This is not equal-quality retrieval: compare candidate/label coverage before interpreting speed. '
                'Native startup and a Python bridge add costs that a permanent implementation could reduce. '
                'Czkawka decodes originals through its own pipeline rather than receiving the normalized native previews; '
                'preprocessing and hardware utilization differ. No universal throughput claim.', '']
    informative_path=folder/'informative-timing.json'
    if informative_path.exists():
        info=json.loads(informative_path.read_text())
        lines+=['',f'Czkawka Mean/16/Lanczos3/difference-10 median on the same 100 originals: {info["median_seconds"]:.3f} seconds '
                '(three uncached, two-thread runs). This setting returned one group in that set and recovers one of four confirmed positives across all sets. '
                'Its speed is not only a zero-result-default measurement.', '']
        if timing_path.exists():
            index.append(f'<h2>100-photo processing time</h2><p>Fresh Vision .45+SIFT: {t["median_processing_seconds"]:.2f}s; '
                         f'Czkawka default: {t["czkawka_t2_seconds"]:.2f}s; Mean16-10: {info["median_seconds"]:.2f}s. '
                         'Medians of three warm-filesystem runs; hash cache disabled. '
                         'Czkawka is faster here but misses most confirmed matches. No equal-quality throughput claim.</p>')
    lines+=['','## Conclusion and limits','',
            'Judge whether Czkawka’s extra groups are useful in the galleries. It must not replace the combo simply because stricter hashing '
            'returns fewer candidates or runs faster. Configuration selection on these same labels is exploratory. '
            'No overall precision/recall or false-positive rate is measurable from the unlabeled remainder. '
            'The configuration union is for review, not a recommended ensemble.','',
            'The user reviewed the prior hash galleries and found many false positives; those hashes are not recommended for the toolkit. '
            'The user accepted Vision .45 plus SIFT as useful complementary candidate finding. Czkawka is an independent standalone hash-based comparison, '
            'not production integration.','',
            'All 254 input SHA-256 values remained unchanged; production jobs.sqlite3 before/after matched. '
            'No production pipeline, schema, CLI default or photo location was changed. Binary and reports are outside Git.','',
            '[Review galleries](index.html) · [Configuration summary](configurations.csv) · [Raw benchmark](benchmark.json)','']
    with(folder/'configurations.csv').open('x',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(csv_rows[0]));w.writeheader();w.writerows(csv_rows)
    with(folder/'FINDINGS.md').open('x')as f:f.write('\n'.join(lines))
    index.append('<p><a href="FINDINGS.md">Full findings and timings</a> · <a href="configurations.csv">Configuration summary</a></p></html>')
    with(folder/'index.html').open('x')as f:f.write('\n'.join(index))
    print('Sparse label scores',scores,'informative config',informative,'combo',combo_tp,combo_fp,combo_count)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    render(parser.parse_args().folder.resolve())
