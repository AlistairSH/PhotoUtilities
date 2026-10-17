"""Portable focus/group review with optional loopback archive controls."""
from __future__ import annotations
import html
import os
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import quote


def render(result: dict[str, Any], destination: Path, created: str) -> str:
    esc=html.escape;images=result['images'];job=result['job_id']
    command=shlex.join(['photo-utils','review',job,'--state-dir',result['state_dir']])
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
    '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; connect-src \'self\'">',
    '<title>Photo focus review</title><style>body{font:16px system-ui;background:#f7f6f2;color:#242a30;max-width:1500px;margin:auto;padding:24px}section{margin:24px 0;padding:18px;background:white;border-radius:8px}.tier-bar{padding:10px 12px;font-weight:bold;border-radius:5px 5px 0 0;background:#e9edf0}.tier-review{background:#dcecff;color:#174f85}.tier-top{background:#d9efdf;color:#216735}.tier-cull{background:#fae4d5;color:#964b13}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}figure{margin:0;border:1px solid #ccc;padding:10px;border-radius:7px}svg{width:100%;height:320px;background:#eee}figcaption{overflow-wrap:anywhere}button{padding:8px 14px;cursor:pointer}.flag{font-weight:bold;color:#a62d1a}.sharper{color:#216735;font-weight:bold}.softer{color:#ad6013;font-weight:bold}.marked{opacity:.55;background:#ffe2dc}.archived{opacity:.4}nav{position:sticky;top:0;background:#f7f6f2;padding:12px;z-index:2;border-bottom:1px solid #aaa}p{line-height:1.5}code{overflow-wrap:anywhere}label{margin-right:12px}.note{color:#505b64;font-size:14px}</style></head><body>',
    f'<h1>Focus and similar-photo review</h1><p>{len(images)} photos · {len(result["groups"])} related sets · {sum(i["focus_review"]["review_suggestion"] for i in images)} focus-review suggestions</p>',
    '<p>Boxes: red - faces, green - people, orange - animals, purple - objects, cyan - attention areas.</p>',
    '<nav><label><input id="boxes" type="checkbox" checked>Show boxes</label><label><input id="flags" type="checkbox">Only focus-review flags</label><button id="archive" disabled>Archive deleted photos</button> <span id="status">No photos marked for deletion.</span></nav>']
    if result.get('archive_enabled'):
        parts.append('<p class="note">Delete marks a selection and can be undone. Archiving verifies a ZIP in PhotoScans/Blurry, then moves selected files and companions out of their active folders. Only the verified ZIP is retained; files can be restored to their original paths. To enable archiving, open this report through the local review command: <code>'+esc(command)+'</code>. No files move while viewing the static report.</p>')
    else:parts.append('<p class="note">Report-only run: archiving is unavailable because this analysis was not saved to the job database.</p>')
    if result.get('tier_version'):
        counts={tier:sum(image['tier_review']['tier']==tier for image in images) for tier in ('Top Pick','Review','Possible Cull')}
        parts.append('<h2>Three-tier selection review</h2><p>'+esc(' · '.join(str(n)+' '+('Keep & Review' if tier=='Review' else tier) for tier,n in counts.items()))+'</p><details><summary>Selection rules</summary><p>'+esc(result['tier_policy'])+'</p></details>')
    def photo(index: int, rank: int, total: int) -> str:
        image=images[index];label=esc(os.path.relpath(image['path'],destination.parent));link=esc(quote(os.path.relpath(image['path'],destination.parent)));review=image['focus_review'];role=image.get('focus_comparison',{}).get('role')
        w,h=image['width'],image['height'];svg=f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{label}"><image width="{w}" height="{h}" href="data:image/jpeg;base64,{image["thumbnail"]}"/><g class="boxes">'
        colors={'faces':'#ff3044','people':'#24dd67','animals':'#ffa700','objectness':'#ad7dff','attention':'#00d9ed'}
        for kind,color in colors.items():
            for n,r in enumerate(image['detectors'][kind].get('regions',[]),1):
                x,y,bw,bh=r.get('display_box',r['box']);svg+=f'<rect x="{x*w}" y="{y*h}" width="{bw*w}" height="{bh*h}" fill="none" stroke="{color}" stroke-width="2"/><text x="{x*w+3}" y="{max(14,y*h+14)}" font-size="14" fill="{color}" stroke="black" stroke-width=".25">{kind} {n}</text>'
        svg+='</g></svg>'
        comparison='<p class="'+str(role)+'">'+('Sharper focus candidate in this group' if role=='sharper' else 'Softer than a similar photo')+'</p>' if role else ''
        tier=image.get('tier_review')
        tier_bar=''
        if tier:
            css={'Top Pick':'tier-top','Review':'tier-review','Possible Cull':'tier-cull'}[tier['tier']]
            tier_bar='<div class="tier-bar '+css+'">'+esc('Keep & Review' if tier['tier']=='Review' else tier['tier'])+'</div>'
            comparison+='<p>'+esc(' '.join(tier['top_pick_reasons']+tier['reasons']+tier['composition_advisories']))+'</p>'
            comparison+='<p>Rank within set: '+str(rank)+'/'+str(total)+'</p>'
        rotation=image.get('rotation',{})
        if rotation.get('quarter_turns_clockwise'): comparison+='<p class="note">Rotated '+str(90*rotation['quarter_turns_clockwise'])+'° clockwise from embedded orientation.</p>'
        flag='Possible Missed Focus' if review['review_suggestion'] else 'Focus review: No'
        # Old saved jobs may retain the former no-flag disclaimer. Gate notes
        # on the flag, rather than matching strings, so re-rendering stays quiet.
        explanation=('<p class="note">'+esc(' '.join(review.get('reason',[])))+'</p>'
                     if review['review_suggestion'] and review.get('reason') else '')
        return f'<figure id="photo-{index}" data-index="{index}" data-review="{str(review["review_suggestion"]).lower()}">{tier_bar}<a class="original" data-index="{index}" href="{link}">{svg}</a><figcaption>{label}</figcaption><p class="{"flag" if review["review_suggestion"] else ""}">{flag}</p>{comparison}{explanation}<button class="delete" data-index="{index}" aria-pressed="false">Delete</button></figure>'
    for level in ('likely','potential'):
        parts.append(f'<h2>{level.capitalize()} groups</h2>')
        for n,g in enumerate(result['groups'],1):
            if g['level']==level:parts.append(f'<section><h3>Set {n}</h3><div class="gallery">'+''.join(photo(i,rank,len(g['members'])) for rank,i in enumerate(g['members'],1))+'</div></section>')
    parts.append('<h2>Ungrouped photos</h2><div class="gallery">'+''.join(photo(i,rank,len(result['unmatched'])) for rank,i in enumerate(result['unmatched'],1))+'</div>')
    parts.append('<p class="note">Analysis '+esc(created)+' · Local Vision + SIFT + Gaussian1 focus review.</p>')
    parts.append('''<script>
const selected=new Set(),archived=new Set();const token=location.hash.slice(1);
const live=location.protocol==='http:'&&token.length>20;
function update(){document.querySelectorAll('figure').forEach(f=>{f.classList.toggle('marked',selected.has(Number(f.dataset.index)));f.hidden=document.getElementById('flags').checked&&f.dataset.review!=='true'});document.querySelectorAll('g.boxes').forEach(e=>e.style.display=document.getElementById('boxes').checked?'':'none');document.getElementById('archive').disabled=!live||!selected.size;document.getElementById('status').textContent=selected.size+' photos marked for deletion.';document.querySelectorAll('button.delete').forEach(b=>{let n=Number(b.dataset.index);b.textContent=selected.has(n)?'Undo delete':'Delete';b.setAttribute('aria-pressed',String(selected.has(n)));b.disabled=archived.has(n)})}
document.querySelectorAll('button.delete').forEach(b=>b.onclick=()=>{let n=Number(b.dataset.index);selected.has(n)?selected.delete(n):selected.add(n);update()});document.querySelectorAll('input').forEach(i=>i.onchange=update);
if(live){document.querySelectorAll('a.original').forEach(a=>a.href='/image/'+a.dataset.index+'?token='+encodeURIComponent(token));fetch('/state',{headers:{Authorization:'Bearer '+token}}).then(r=>r.json()).then(s=>{(s.archived_indices||[]).forEach(n=>{archived.add(n);document.getElementById('photo-'+n).classList.add('archived')});update()}).catch(()=>{})}
document.getElementById('archive').onclick=async()=>{const indices=Array.from(selected);if(!confirm('Archive '+indices.length+' selected photos and their companions? Files will move out of active folders after ZIP verification.'))return;document.getElementById('archive').disabled=true;document.getElementById('status').textContent='Verifying and archiving…';try{let r=await fetch('/archive',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({indices})});let d=await r.json();if(!r.ok)throw Error(d.error||'Archive failed');indices.forEach(n=>{selected.delete(n);archived.add(n);document.getElementById('photo-'+n).classList.add('archived')});update();document.getElementById('status').textContent='Archived '+d.files+' files. Restore with: '+d.restore_command+(d.cleanup_warning?' Duplicate cleanup needs attention: '+d.cleanup_warning:'');}catch(e){update();document.getElementById('status').textContent=e.message}};
update();
</script></body></html>''')
    document = '\n'.join(parts)
    if result.get('tier_version'):
        document = document.replace('<title>Photo focus review</title>','<title>Three-tier photo review</title>').replace('<h1>Focus and similar-photo review</h1>','<h1>Three-tier photo review</h1>')
    document = document.replace('objectness', 'object').replace('Objectness', 'Object')
    return document
