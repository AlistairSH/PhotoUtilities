"""Isolated offline aesthetics trial. No canonical DB writes or CLI integration."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import math
import platform
import resource
import selectors
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from photo_utils.similarity import analyze, collect_images

VERSION = 'apple-aesthetics-experiment-v1'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path: Path, value: Any) -> None:
    # Checkpoints use atomic replacement only inside this run's exclusive folder.
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False))
    temporary.replace(path)


def rank_groups(result: dict[str, Any]) -> list[dict[str, Any]]:
    images = result['images']
    output = []
    for number, group in enumerate(result['groups'], 1):
        members = group['members']
        pairs = [p for p in result['pairs'] if p['a'] in members and p['b'] in members]
        direct = {tuple(sorted((p['a'], p['b']))) for p in pairs if p['level'] != 'unmatched'}
        chained = len(direct) < len(members) * (len(members)-1) // 2
        weak = any(p['level'] == 'potential' for p in pairs)
        scores = {i: images[i]['aesthetics']['overallScore'] for i in members if images[i]['aesthetics']['status'] == 'ok'}
        ordered = sorted(scores, key=lambda i: (-scores[i], i))
        # Experimental eligibility only for fully directly matched groups. A
        # retained competitor must directly dominate the candidate; never chain.
        excluded: dict[int, list[int]] = {}
        if not chained and not weak:
            for i in members:
                comparison = images[i].get('focus_comparison') or {}
                if comparison.get('role') == 'softer':
                    witnesses = [j for j in comparison.get('softer_than', []) if j in scores
                                 and tuple(sorted((i, j))) in direct
                                 and (images[j].get('focus_comparison') or {}).get('role') == 'sharper']
                    if witnesses:
                        excluded[i] = witnesses
        eligible = [i for i in ordered if i not in excluded]
        gap = scores[ordered[0]] - scores[ordered[1]] if len(ordered) > 1 else None
        incomplete = len(scores) != len(members)
        tied = len(ordered)>1 and gap == 0
        review = chained or weak or incomplete or tied or not ordered
        output.append({**group, 'id':group.get('id', f'group-{number:03d}'), 'direct_pairs':pairs,
            'chained':chained, 'weak':weak, 'incomplete':incomplete, 'exact_tie':tied,
            'ranking_a':ordered, 'ranking_b':eligible, 'ranking_c':ordered,
            'excluded':excluded, 'gap':gap,
            'winner_a': ordered[0] if ordered and not review else None,
            'winner_b': eligible[0] if eligible and not review else None,
            'winner_c': ordered[0] if ordered and not review else None,
            'explanation': 'Review manually: potentially non-interchangeable weak/chained group.' if chained or weak else
                'No recommendation: incomplete scores.' if incomplete else
                'No clear recommendation: exact score tie.' if tied else 'Highest Apple aesthetic score in group.',
            'eligibility_explanation': 'Eligibility withheld for weak/chained groups.' if chained or weak else
                'Highest aesthetic score among candidates without applicable direct inferior-focus evidence.'})
    return output


def render(result: dict[str, Any]) -> str:
    esc = html.escape
    sections = []
    for group in result['comparisons']:
        cards = []
        for i in group['members']:  # Never sort the blind display by score.
            image = result['images'][i]; score = image['aesthetics']; name = Path(image['path']).name
            preview = score.get('preview', image.get('thumbnail', ''))
            focus = image.get('focus_review', {})
            comp = image.get('focus_comparison') or {}
            focus_text = '; '.join(focus.get('reason', [])) if focus.get('review_suggestion') else 'No review trigger; sharpness unassessed.'
            evidence = ', '.join(Path(result['images'][j]['path']).name for j in comp.get('softer_than', []))
            ranks = {key: (group[key].index(i)+1 if i in group[key] else 'ineligible/unavailable') for key in ('ranking_a','ranking_b')}
            value = f"{score['overallScore']:.6f}; utility: {score['isUtility']}" if score['status']=='ok' else 'Failed: '+score['error']
            cards.append(f'''<article><a href="{esc(Path(image['path']).as_uri(), quote=True)}"><img src="data:image/jpeg;base64,{preview}" alt="{esc(name, quote=True)}"></a>
                <p>{esc(name)}</p><label><input type="radio" name="{group['id']}" value="{i}"> My preferred image</label>
                <div class="model" hidden><p>Apple: {esc(value)}</p><p>A/C rank: {ranks['ranking_a']} · B rank: {ranks['ranking_b']}</p>
                <p>Focus advisory: {esc(focus_text)}</p><p>Relative focus: {esc(str(comp.get('role') or 'no applicable highlight'))}{(' · softer than '+esc(evidence)) if evidence else ''}</p></div></article>''')
        def choice(key: str) -> str:
            value = group[key]
            return Path(result['images'][value]['path']).name if value is not None else 'Withheld; review manually'
        pair_rows = ''.join(f"<li>{esc(Path(result['images'][p['a']]['path']).name)} ↔ {esc(Path(result['images'][p['b']]['path']).name)}: {p['level']}; Vision {p['vision_distance']:.4f}; SIFT {p['sift_candidate']}</li>" for p in group['direct_pairs'])
        sections.append(f'''<section id="{group['id']}"><h2>{group['id']} · {len(group['members'])} photographs</h2>
          <p>Choose independently, then reveal the comparison. Category labels are optional human annotations.</p><div class="cards">{''.join(cards)}</div>
          <label><input type="radio" name="{group['id']}" value="none"> No clear winner</label>
          <p><select class="category"><option value="unknown">Category unknown</option><option>People / portraits</option><option>Multiple people</option><option>Landscape / outdoors</option><option>Buildings</option><option>Other</option></select>
          <input class="notes" placeholder="Optional notes" aria-label="Notes"></p>
          <button class="reveal">Reveal model comparison after choosing</button>
          <div class="model" hidden><p>A · aesthetics only: {esc(choice('winner_a'))}<br>B · conservative focus eligibility: {esc(choice('winner_b'))}<br>C · aesthetics with advisory: {esc(choice('winner_c'))}</p>
          <p>{esc(group['explanation'])} Top-two gap: {group['gap'] if group['gap'] is not None else 'unavailable'}. No calibrated confidence threshold.</p>
          <p>{esc(group['eligibility_explanation'])} Small score gaps may not reflect a meaningful preference.</p>
          <label>Model assessment <select class="assessment"><option value="">Not assessed</option><option>Reasonable</option><option>Incorrect</option></select></label>
          <details><summary>Direct-pair similarity evidence</summary><ul>{pair_rows}</ul></details></div></section>''')
    if result.get('unmatched'):
        cards=''.join(f'<article><a href="{esc(Path(result["images"][i]["path"]).as_uri(),quote=True)}"><img src="data:image/jpeg;base64,{result["images"][i]["aesthetics"].get("preview",result["images"][i].get("thumbnail",""))}" alt="Ungrouped photograph"></a><p>{esc(Path(result["images"][i]["path"]).name)}</p></article>' for i in result['unmatched'])
        sections.append('<aside><h2>Unexpectedly ungrouped photographs</h2><p>You indicated that every sample has a neighbor. These images did not connect under the accepted matching rule. No winner is assigned.</p><div class="cards">'+cards+'</div></aside>')
    metadata = json.dumps({'experiment_id':result['experiment_id'], 'version':VERSION, 'groups':[g['id'] for g in result['comparisons']]})
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Blind Apple aesthetics trial</title>
<style>body{font:16px system-ui;margin:24px;background:#f5f4f0;color:#242424}header{position:sticky;top:0;background:#f5f4f0;padding:12px;z-index:2;border-bottom:1px solid #bbb}section{background:white;padding:20px;margin:24px 0;border-radius:12px}.cards{display:flex;flex-wrap:wrap;gap:18px}article{flex:1 1 360px;max-width:650px}img{width:100%;height:420px;object-fit:contain;background:#eee}button,select,input{font:inherit}button{padding:10px;margin:8px}input.notes{width: min(600px,80%)}[hidden]{display:none!important}p{line-height:1.5}#status{font-weight:600}</style>
<header><h1>Blind Apple aesthetics trial</h1><p>Original images remain unchanged. Pick one image or “No clear winner” before revealing scores. A/C use the same ranking; C adds focus advice. B tests conservative direct focus exclusions.</p><button id="export">Export evaluations JSON</button><label>Import saved evaluations <input id="import" type="file" accept=".json"></label><span id="status"></span><p id="storage"></p></header>
''' + ''.join(sections) + '''<script>
const META=''' + metadata.replace('<', '\\u003c') + ''';
const KEY='aesthetics-'+META.experiment_id;let answers={};let storageOK=true;
try{answers=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){storageOK=false}
const sections=[...document.querySelectorAll('section')];
function update(){document.querySelector('#status').textContent=Object.values(answers).filter(a=>a.choice!==undefined).length+' / '+META.groups.length+' selected';document.querySelector('#storage').textContent=storageOK?'Saved in this browser; export JSON before closing or switching browsers.':'Browser storage unavailable: export JSON before closing.'}
function persist(){try{localStorage.setItem(KEY,JSON.stringify(answers))}catch(e){storageOK=false}update()}
function apply(){for(const s of sections){const a=answers[s.id]||{};for(const r of s.querySelectorAll('input[type=radio]'))r.checked=String(a.choice)===r.value;s.querySelector('.category').value=a.category||'unknown';s.querySelector('.notes').value=a.notes||'';s.querySelector('.assessment').value=a.assessment||'';for(const m of s.querySelectorAll('.model'))m.hidden=!a.revealed;s.querySelector('.reveal').disabled=a.choice===undefined||!!a.revealed}update()}
for(const s of sections){s.addEventListener('change',e=>{const a=answers[s.id]||{};const selected=s.querySelector('input[type=radio]:checked');if(selected){const choice=selected.value==='none'?'none':Number(selected.value);if(a.revealed&&choice!==a.choice)a.changed_after_reveal=true;a.choice=choice}a.category=s.querySelector('.category').value;a.assessment=s.querySelector('.assessment').value;answers[s.id]=a;persist();apply()});s.querySelector('.notes').addEventListener('input',e=>{answers[s.id]={...(answers[s.id]||{}),notes:e.target.value};persist()});s.querySelector('.reveal').onclick=()=>{const a=answers[s.id];if(!a||a.choice===undefined)return;if(a.blind_choice===undefined)a.blind_choice=a.choice;a.revealed=true;persist();apply()}}
document.querySelector('#export').onclick=()=>{const data={...META,exported_at:new Date().toISOString(),answers};const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='aesthetics-evaluations.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
document.querySelector('#import').onchange=async e=>{try{const data=JSON.parse(await e.target.files[0].text());if(data.experiment_id!==META.experiment_id)throw Error('Different experiment');answers=data.answers;persist();apply()}catch(err){alert('Cannot import: '+err.message)}};apply();
</script></html>'''


def score_rows(paths: list[Path], helper: Path, error_path: Path, checkpoint: Path, timeout: float = 600) -> list[dict[str, Any]]:
    scores: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout
    with error_path.open('w') as errors:
        process = subprocess.Popen([str(helper)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        selector = selectors.DefaultSelector()
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(list(map(str,paths))).encode());process.stdin.close()
            selector.register(process.stdout, selectors.EVENT_READ)
            buffer = bytearray(); complete = False
            while True:
                remaining = deadline-time.monotonic()
                if remaining<=0 or not selector.select(remaining): raise ValueError('Native aesthetics timed out')
                chunk = os.read(process.stdout.fileno(),1024*1024)
                if not chunk: break
                buffer.extend(chunk)
                if len(buffer)>16*1024*1024:raise ValueError('Native aesthetics row exceeded limit')
                while b'\n' in buffer:
                    line, _, remainder = buffer.partition(b'\n');buffer=bytearray(remainder)
                    row=json.loads(line)
                    if complete:raise ValueError('Output after completion')
                    if row.get('type')=='complete':
                        if row['images']!=len(paths):raise ValueError('Invalid native completion count')
                        complete=True;continue
                    i=len(scores)
                    if i>=len(paths) or row['index']!=i or row['path']!=str(paths[i]):raise ValueError('Native identity mismatch')
                    if row['status'] not in ('ok','failed'):raise ValueError('Invalid native status')
                    if row['status']=='ok' and (not math.isfinite(row['overallScore']) or not -1<=row['overallScore']<=1):raise ValueError('Invalid score')
                    scores.append(row);save(checkpoint,scores)
                    print(f'Aesthetics {len(scores)}/{len(paths)}: {row["status"]}',flush=True)
            if buffer or process.wait(timeout=max(.1,deadline-time.monotonic()))!=0 or not complete or len(scores)!=len(paths):
                raise ValueError('Incomplete native scoring; see native-errors.txt')
        finally:
            selector.close()
            if process.poll() is None:process.kill();process.wait()
            if process.stdout is not None:process.stdout.close()
            if process.stdin is not None and not process.stdin.closed:process.stdin.close()
    return scores


def run(args: argparse.Namespace) -> None:
    started = time.monotonic()
    paths = collect_images([args.folder], skip_generated=True)
    paths = [p for p in paths if not p.is_symlink()]
    output = args.output_dir.resolve()
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents:
        raise ValueError('Private results must be outside the repository')
    output.mkdir(parents=True, exist_ok=False)
    hashes = [digest(p) for p in paths]
    manifest = {'version':VERSION,'experiment_id':str(uuid.uuid4()),'paths':list(map(str,paths)),
                'hashes':hashes,'status':'running','os':platform.platform(),
                'scorer_sha256':digest(Path(__file__).with_name('scorer.swift')),
                'helper_sha256':digest(args.helper),'implementation_sha256':digest(Path(__file__))}
    save(output/'run.json',manifest)
    try:
        grouping_start=time.monotonic()
        result = analyze(paths, hashes, focus=True)
        result['grouping_seconds']=time.monotonic()-grouping_start
        save(output/'grouping.json',result)
        scores = score_rows(paths, args.helper, output/'native-errors.txt', output/'scores.partial.json')
        # Read existing identities by matching content, without touching SQLite.
        if args.database.is_file():
            with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as db:
                identities={}
                for asset_id,path,sha in db.execute('SELECT asset_id,path,sha256 FROM assets'):
                    identities.setdefault(sha,[]).append({'asset_id':asset_id,'historical_path':path})
                for image in result['images']:image['existing_assets']=identities.get(image['sha256'],[])
        for image,score in zip(result['images'],scores):image['aesthetics']=score
        result.update(manifest)
        result['comparisons']=rank_groups(result)
        if hashes != [digest(p) for p in paths]:raise ValueError('Source checksum changed; refusing publication')
        result['status']='complete';result['seconds']=time.monotonic()-started
        result['python_peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result['max_child_peak_rss_bytes']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        result['summary']={'images':len(paths),'groups':len(result['groups']),'unmatched':len(result['unmatched']),
            'failed_scores':sum(s['status']!='ok' for s in scores),
            'chained_groups':sum(g['chained'] for g in result['comparisons']),
            'weak_groups':sum(g['weak'] for g in result['comparisons']),
            'changed_winners':sum(g['winner_a']!=g['winner_b'] for g in result['comparisons']),
            'excluded_candidates':sum(len(g['excluded']) for g in result['comparisons'])}
        save(output/'results.json',result)
        report=output/'review.html';temporary=output/'review.html.partial';temporary.write_text(render(result));temporary.replace(report)
        save(output/'run.json',{**manifest,'status':'complete','summary':result['summary'],'seconds':result['seconds']})
        print(json.dumps(result['summary'])); print(f'Report: {report}')
    except BaseException as exc:
        save(output/'run.json',{**manifest,'status':'interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed','error':str(exc)})
        raise


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--helper',type=Path,required=True)
    parser.add_argument('--database',type=Path,default=Path.home()/'Library/Application Support/PhotoUtilities/jobs.sqlite3')
    run(parser.parse_args())

if __name__=='__main__':main()
