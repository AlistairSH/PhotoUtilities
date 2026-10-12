"""Provisional subject-aware review evidence; not a calibrated blur classifier."""
import argparse
import collections
import csv
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from run import digest

VERSION='subject-review-v2'
POLICY={'version':VERSION,'subject_rule':'Laplacian and Tenengrad region/outside ratios below 1 at both 1024 and 2048; matching region IoU >= .5',
        'minimum_region_side':24,'semantic_order':['faces','people','animals','objectness'],
        'attention_role':'Use as uncertain focus region only when no usable face/person/animal/objectness region exists',
        'global_rule':'All six global/strongest-tile signals in the batch bottom 10%, ties counted conservatively',
        'severe_blur_threshold':None,'status':'Unvalidated diagnostic evidence for manual review; no automatic culling'}


def overlap(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    area=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
    total=aw*ah+bw*bh-area
    return area/total if total>0 else 0


def low_detail(region):
    measured=region.get('smoothed')
    if not region['usable'] or not measured or not measured['outside']:return False
    ratios=measured['region_to_outside']
    return all(ratios.get(key) is not None and ratios[key]<1 for key in ('laplacian_variance','tenengrad'))


def subject_evidence(small,large):
    cues=[]
    attention_only=not any(r['usable'] and not r['id'].startswith('attention') for r in small['focus']['regions'])
    for region in small['focus']['regions']:
        kind=region['id'].split()[0]
        if (kind=='attention' and not attention_only) or not low_detail(region):continue
        alternatives=[r for r in large['focus']['regions'] if r['id'].split()[0]==kind]
        if not alternatives:continue
        match=max(alternatives,key=lambda r:overlap(r['box'],region['box']))
        if overlap(match['box'],region['box'])<.5 or not low_detail(match):continue
        cues.append({'region':region['id'],'box':region['box'],'matching_region_2048':match['id'],
                     'ratios_1024':region['smoothed']['region_to_outside'],
                     'ratios_2048':match['smoothed']['region_to_outside'],
                     'reason':(f'{region["id"]} is an uncertain attention-only focus fallback; subject identity is unknown. '
                               if kind=='attention' else '')+f'{region["id"]} has less measured detail than outside pixels in both metrics at both resolutions.'})
    priority={name:i for i,name in enumerate(POLICY['semantic_order'])}
    priority['attention']=len(priority)
    return sorted(cues,key=lambda c:priority[c['region'].split()[0]])


def screen(rows):
    paths=list(dict.fromkeys(r['path'] for r in rows))
    paired={path:{r['max_dimension']:r for r in rows if r['path']==path} for path in paths}
    signals=[]
    for path in paths:
        scales=paired[path]
        if set(scales)!={1024,2048}:raise ValueError('Requires both input resolutions')
        values={}
        for scale,row in scales.items():
            global_values=row['focus']['global']['smoothed']
            for metric in ('laplacian_variance','tenengrad'):values[f'{scale}/{metric}']=global_values[metric]
            values[f'{scale}/peak_tile_tenengrad']=max(row['focus']['tile_tenengrad'])
        signals.append(values)
    reference={key:sorted(v[key] for v in signals) for key in signals[0]}
    decisions=[]
    for path,values in zip(paths,signals):
        cues=subject_evidence(paired[path][1024],paired[path][2048])
        fractions={key:sum(v<=values[key] for v in ref)/len(paths) for key,ref in reference.items()}
        global_low=len(paths)>=20 and all(v<=.1 for v in fractions.values())
        reasons=[cue['reason'] for cue in cues]
        if global_low:reasons.append('Low global detail and low strongest-tile detail across both resolutions in this reference batch.')
        contradictory=[]
        # Keep contrary regions visible rather than treating a detail ratio as a
        # focus verdict or letting one sharp person clear every other subject.
        for r in paired[path][1024]['focus']['regions']:
            ratio=r['smoothed']['region_to_outside'] if r.get('smoothed') else {}
            if r['id'].split()[0] in ('faces','people','animals') and all(ratio.get(k,0)>=1 for k in ('laplacian_variance','tenengrad')):
                contradictory.append(r['id'])
        decisions.append({'path':path,'review_suggestion':bool(cues) or global_low,'category':'manual_review' if cues or global_low else 'unassessed',
                          'subject_cues':cues,'global_low_detail':global_low,'contrary_regions':contradictory,
                          'reason':reasons or ['No consistent low-detail evidence under this rule; focus is not certified acceptable.'],
                          'global_measurements':values,'global_lower_tail_fractions':fractions,'severe_blur_candidate':False})
    return decisions


def make_report(source_html,rows,decisions,destination):
    escape=html.escape
    links=[]
    by_path={d['path']:d for d in decisions}
    for d in decisions:
        if not d['review_suggestion']:continue
        name=Path(d['path']).name
        links.append(f'<li><a href="#{name}">{escape(Path(d["path"]).parent.name+" / "+name)}</a>: '+escape(' '.join(d['reason']))+'</li>')
    # Reuse the full regional focus report, adding a navigation shortlist and
    # decision explanations. No thumbnails or originals are modified.
    folders=sorted({Path(d['path']).parent.name for d in decisions})
    source_html=source_html.replace('<h1>Subject-region focus experiment</h1>',
        '<h1>Subject-aware focus review</h1>'
        f'<p>{len(decisions)} images. Included source folders: {escape(", ".join(folders))}. Only these folders were analyzed.</p>'
        f'<p>{len(links)} provisional review suggestions. Subject regions must show lower detail in both metrics at both resolutions; attention is a fallback only if no usable semantic/objectness region exists. '
        'Global low-detail sampling is also included. Ratios reflect texture and contrast as well as focus. No image is declared acceptable or severely blurred.</p>'
        '<details open><summary>Review shortlist</summary><ul>'+''.join(links)+'</ul></details>')
    for path,d in by_path.items():
        name=Path(path).name
        marker=f'<section><h2>{escape(name)}</h2>'
        text=f'<p><strong>{"REVIEW SUGGESTION" if d["review_suggestion"] else "Unassessed"}</strong>: {escape(" ".join(d["reason"]))}</p>'
        if d['contrary_regions'] and d['review_suggestion']:
            text+='<p>Contrary detail evidence in '+escape(', '.join(d['contrary_regions']))+'. Inspect multiple subjects and texture before interpreting this flag.</p>'
        source_html=source_html.replace(marker,f'<section id="{escape(name)}"><h2>{escape(name)}</h2>'+text)
    return source_html


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--focus',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args()
    focus=json.loads(args.focus.read_text())
    paths=[Path(p) for p in focus['source_paths']]
    if any(p.is_symlink() for p in paths) or focus['source_sha256']!=[digest(p) for p in paths]:raise ValueError('Source identity mismatch')
    output=args.output_dir.resolve();repository=Path(__file__).resolve().parents[2]
    if output==repository or repository in output.parents or any(output==p.parent or p.parent in output.parents for p in paths):raise ValueError('Unsafe output location')
    decisions=screen(focus['rows'])
    source_html=(args.focus.parent/'region-focus.html').read_text()
    # Reports are sibling folders at the same depth, but rewrite links explicitly.
    for path in paths:
        old=html.escape(quote(os.path.relpath(path,args.focus.parent)))
        new=html.escape(quote(os.path.relpath(path,output)))
        source_html=source_html.replace(f'href="{old}"',f'href="{new}"')
    document=make_report(source_html,focus['rows'],decisions,output/'review.html')
    if focus['source_sha256']!=[digest(p) for p in paths]:raise ValueError('Sources changed')
    output.mkdir(parents=True,exist_ok=False)
    (output/'review.html').write_text(document)
    payload={'version':VERSION,'policy':POLICY,'focus_export':str(args.focus.resolve()),
             'focus_export_sha256':digest(args.focus),'inputs_unchanged':True,
             'source_sha256':focus['source_sha256'],'images':decisions}
    (output/'review-manifest.json').write_text(json.dumps(payload,indent=2))
    with (output/'review.csv').open('x',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['path','review_suggestion','region_evidence','human_assessment','notes'])
        for d in decisions:writer.writerow([d['path'],d['review_suggestion'],'; '.join(c['region'] for c in d['subject_cues']),'',''])
    print('Images',len(decisions),'review suggestions',sum(d['review_suggestion'] for d in decisions),'global low detail',sum(d['global_low_detail'] for d in decisions))
    print('By roll',dict(collections.Counter(Path(d['path']).parent.name for d in decisions if d['review_suggestion'])))
    print('Saved:',output/'review.html')


if __name__=='__main__':main()
