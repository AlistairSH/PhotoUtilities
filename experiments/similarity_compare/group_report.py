"""Connected-set report for the fixed Vision <.45 OR strict SIFT experiment."""
import argparse
import csv
import html
import json
import os
from pathlib import Path
from urllib.parse import quote


def accepted(pair):
    return pair['vision_distance'] < 0.45 or pair['sift_candidate']


def components(count, edges):
    neighbors = [set() for _ in range(count)]
    for a, b in edges:
        neighbors[a].add(b)
        neighbors[b].add(a)
    seen = set()
    groups = []
    for start in range(count):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        members = []
        while stack:
            item = stack.pop()
            members.append(item)
            for other in sorted(neighbors[item]):
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        groups.append(sorted(members))
    groups.sort(key=lambda g: (-len(g), g))
    return groups, neighbors


def bridges(members, edges):
    """Links whose removal splits this candidate component; not proof of error."""
    base, _ = components(max(members)+1, edges)
    initial = sum(bool(set(group) & set(members)) for group in base)
    result = set()
    for edge in edges:
        groups, _ = components(max(members)+1, [e for e in edges if e != edge])
        after = sum(bool(set(group) & set(members)) for group in groups)
        if after > initial:
            result.add(edge)
    return result


def render(comparison, output):
    data = json.loads(comparison.read_text())
    images = data['images']
    count = len(images)
    if len(data['pairs']) != count*(count-1)//2:
        raise ValueError('Incomplete pair coverage')
    edges = {(p['a'],p['b']): p for p in data['pairs'] if accepted(p)}
    groups, neighbors = components(count, list(edges))
    matched = [g for g in groups if len(g)>1]
    singles = [g[0] for g in groups if len(g)==1]
    large = [g for g in matched if len(g)>3]
    def name(i): return Path(images[i]['path']).name
    def image_tag(i):
        path = Path(images[i]['path'])
        src = quote(os.path.relpath(path, output))
        return f'<figure><a href="{src}"><img loading="lazy" src="{src}" alt="{html.escape(path.name)}"></a><figcaption>{html.escape(path.name)} · {len(neighbors[i])} direct links</figcaption></figure>'
    def support(p):
        v = p['vision_distance'] < .45
        return 'Vision + SIFT' if v and p['sift_candidate'] else ('Vision' if v else 'SIFT only')
    lines = ['# SimilarityTests: candidate sets', '',
             f'{count} edited color images; {len(data["pairs"]):,} pair comparisons. Fixed rule: Vision revision 2 distance <0.45 OR the previously tested strict SIFT candidate rule. No hash scores contribute.', '',
             f'**{len(matched)} matched sets; {len(singles)} unpaired photographs; {len(large)} sets larger than three.** '
             f'{len(edges)} direct candidate links; {sum(len(g)for g in matched)}/{count} photographs have at least one accepted link.', '',
             'The user states every image has a genuine partner. Therefore each unpaired photograph below is a known retrieval gap at these fixed settings. '
             'Matched membership is not proof that every intended pair was recovered or that every link is correct; full ground-truth group labels were not supplied.', '',
             'Groups are connected components: chaining is allowed. A–B and B–C puts A/B/C in one set even if A–C does not match directly. '
             'Every direct link is listed; bridge links are marked for review because removing one splits the candidate set.', '',
             '## Sets larger than three', '']
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SimilarityTests: Vision .45 + SIFT sets</title>',
             '<style>body{font:16px system-ui;background:#17191d;color:#eee;max-width:1350px;margin:30px auto;padding:20px}a{color:#9ecaff}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px;margin-bottom:24px}figure{margin:0}img{width:100%;height:260px;object-fit:contain;background:#08090b}h2{margin-top:45px}.important{padding:15px;border:2px solid #e6b852;background:#29251c}table{border-collapse:collapse;width:100%;margin-bottom:30px}td,th{padding:8px;border:1px solid #4c5159;text-align:left}summary{cursor:pointer;padding:10px;background:#252b34}</style>',
             '<h1>SimilarityTests — Vision .45 + SIFT</h1>',
             f'<p class="important">{count} photos · {len(matched)} candidate sets · <b>{len(singles)} unpaired photos</b> · <b>{len(large)} sets larger than three</b> · {len(edges)} direct links.</p>',
             '<p>Original photographs displayed locally, unchanged. Click an image to open the original. '
             'The rule is unchanged from previous runs: Vision distance &lt;0.45 OR strict SIFT. Hash scores are ignored.</p>',
             '<p>Sets allow chaining; membership does not mean every pair matches directly. '
             'Bridge links split a group if removed and deserve review. Because you supplied no partner identities, '
             'matched sets cannot yet establish complete recall or accuracy.</p>',
             '<p><a href="#unpaired">Jump to unpaired photos</a> · <a href="FINDINGS.md">Written findings</a> · <a href="groups.json">Machine-readable groups</a></p>']
    group_records = []
    for number, members in enumerate(matched, 1):
        member_set = set(members)
        inside = {edge: p for edge,p in edges.items() if edge[0] in member_set and edge[1] in member_set}
        bridge_links = bridges(members, list(inside))
        missing = len(members)*(len(members)-1)//2-len(inside)
        record = {'group': number, 'size': len(members), 'members': [name(i)for i in members],
                  'complete_direct_clique': missing==0, 'unmatched_internal_pairs': missing,
                  'edges': [{'a': name(a), 'b': name(b), 'support': support(p),
                             'vision_distance': p['vision_distance'], 'sift_inliers': p['inliers'],
                             'coverage_a': p['coverage_a'], 'coverage_b': p['coverage_b'],
                             'bridge': (a,b)in bridge_links}for (a,b),p in inside.items()]}
        group_records.append(record)
        if len(members)>3:
            lines += [f'### Set {number}: {len(members)} photos', '', ', '.join(name(i)for i in members), '',
                      f'{len(inside)} of {len(members)*(len(members)-1)//2} internal pairs match directly; '
                      f'{len(bridge_links)} bridge links. '+('Every internal pair matches directly.' if not missing else 'This is a chained set, not a complete direct-match group.'), '']
        parts += [f'<h2 id="group-{number}"'+(' class="important"'if len(members)>3 else '')+f'>Set {number} — {len(members)} photos</h2>',
                  f'<p>{len(inside)} direct links; {missing} internal pairs do not pass the rule; {len(bridge_links)} bridge links.</p>',
                  '<div class="gallery">']
        parts += [image_tag(i)for i in members]
        parts += ['</div><details'+(' open'if len(members)>3 else '')+'><summary>Direct links and evidence</summary>',
                  '<table><tr><th>Photo A</th><th>Photo B</th><th>Support</th><th>Vision distance</th><th>SIFT inliers</th><th>Min SIFT coverage</th><th>Bridge</th></tr>']
        for (a,b),p in sorted(inside.items()):
            parts.append(f'<tr><td>{html.escape(name(a))}</td><td>{html.escape(name(b))}</td><td>{support(p)}</td><td>{p["vision_distance"]:.3f}</td><td>{p["inliers"]}</td><td>{100*min(p["coverage_a"],p["coverage_b"]):.1f}%</td><td>{"Yes"if(a,b)in bridge_links else ""}</td></tr>')
        parts.append('</table></details>')
    if not large: lines += ['None. The expected approximately ten-photo series was not recovered as a >3-photo set.', '']
    lines += ['## All matched sets', '', '| Set | Size | Members |', '| --- | ---: | --- |']
    for record in group_records:lines.append(f'| {record["group"]} | {record["size"]} | '+', '.join(record['members'])+' |')
    lines += ['', '## Unpaired photographs and nearest evidence', '']
    parts += ['<h2 id="unpaired" class="important">Unpaired photographs — '+str(len(singles))+'</h2>',
              '<p>Each has zero accepted links. The nearest comparisons below failed the current fixed rule; they are diagnostic candidates, not assigned partners.</p>']
    single_records=[]
    for i in singles:
        related=[p for p in data['pairs']if i in(p['a'],p['b'])]
        nearest=sorted(related,key=lambda p:p['vision_distance'])[:3]
        strongest=sorted(related,key=lambda p:-p['sift_strength'])[:2]
        selected=nearest+[p for p in strongest if p not in nearest]
        entries=[]
        lines += [f'### {name(i)}', '', '| Candidate partner | Vision distance | SIFT inliers | Inlier fraction | Minimum coverage |', '| --- | ---: | ---: | ---: | ---: |']
        parts += ['<h3>'+html.escape(name(i))+'</h3><div class="gallery">'+image_tag(i)+'</div>',
                  '<table><tr><th>Nearest/strongest candidate</th><th>Vision</th><th>SIFT inliers</th><th>Inlier fraction</th><th>Min coverage</th></tr>']
        for p in selected:
            other=p['b']if p['a']==i else p['a'];minimum=min(p['coverage_a'],p['coverage_b'])
            entries.append({'partner':name(other),'vision_distance':p['vision_distance'],'sift_inliers':p['inliers'],'sift_inlier_fraction':p['inlier_fraction'],'min_coverage':minimum})
            lines.append(f'| {name(other)} | {p["vision_distance"]:.3f} | {p["inliers"]} | {p["inlier_fraction"]:.3f} | {minimum:.3f} |')
            src=quote(os.path.relpath(Path(images[other]['path']),output))
            parts.append(f'<tr><td><a href="{src}">{html.escape(name(other))}</a></td><td>{p["vision_distance"]:.3f}</td><td>{p["inliers"]}</td><td>{p["inlier_fraction"]:.3f}</td><td>{minimum:.3f}</td></tr>')
        lines.append('');parts.append('</table>');single_records.append({'filename':name(i),'candidates':entries})
    if not singles: lines += ['None: every image has at least one candidate link. This does not prove every intended pair/group was correctly recovered.', '']
    method_counts={'vision_only':sum(support(p)=='Vision'for p in edges.values()),
                   'sift_only':sum(support(p)=='SIFT only'for p in edges.values()),
                   'both':sum(support(p)=='Vision + SIFT'for p in edges.values())}
    result={'images':count,'pairs':len(data['pairs']),'matched_sets':len(matched),'unpaired':single_records,
            'larger_than_three':sum(len(g)>3 for g in matched),'groups':group_records,
            'edge_support':method_counts,'rule':'Vision distance <0.45 OR strict SIFT; connected components'}
    with(output/'groups.json').open('x')as f:json.dump(result,f,indent=2)
    with(output/'all-pairs.csv').open('x',newline='')as f:
        fields=['filename_a','filename_b','candidate','support','vision_distance','sift_candidate','inliers','inlier_fraction','coverage_a','coverage_b']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for p in data['pairs']:
            row={k:p[k]for k in fields if k in p}
            row.update({'filename_a':name(p['a']),'filename_b':name(p['b']),'candidate':accepted(p),'support':support(p)if accepted(p)else'none'})
            writer.writerow(row)
    lines += ['## Methods and limits', '',
              f'Direct links: {method_counts["vision_only"]} Vision-only, {method_counts["sift_only"]} SIFT-only, {method_counts["both"]} both.', '',
              'SIFT settings remain fixed: 500 features, mutual .75 ratio matches, RANSAC at 3 pixels, ≥12 inliers, '
              '≥.5 inlier fraction, ≥.10 coverage in both frames. A large zoom change can leave too little coverage '
              'in the wider frame even when the subject is shared. Moving subjects, parallax and edits can also break geometric support. '
              'A chain can also connect different scenes through an erroneous bridge; review large sets carefully.', '',
              'Source pixels, file locations, production pipeline and SQLite are unchanged. Integrity results are in integrity.json. '
              'Only numeric analysis ran locally; private images were not sent for cloud/model visual review. '
              'No threshold tuning, new hash signal or automatic culling was applied.', '',
              '[Group gallery](review.html) · [Machine-readable sets](groups.json) · [Every pair](all-pairs.csv)', '']
    parts.append('<p>No photo edits, moves, deletion or best-frame selection. <a href="all-pairs.csv">All pair evidence</a>.</p></html>')
    with(output/'FINDINGS.md').open('x')as f:f.write('\n'.join(lines))
    with(output/'review.html').open('x')as f:f.write('\n'.join(parts))
    print('Matched sets',len(matched),'unpaired',len(singles),'large set sizes',[len(g)for g in large],method_counts)
    for record in group_records:print('Set',record['group'],record['size'],', '.join(record['members']))
    print('Unpaired:',', '.join(name(i)for i in singles))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('comparison',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();render(args.comparison,args.output.resolve())
