"""Offline CLIP ViT-L/14 + Schuhmann checkpoint, isolated from routine CLI."""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import importlib.metadata
import io
import json
import math
import platform
import resource
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def save(path: Path, value: Any) -> None:
    partial=path.with_suffix(path.suffix+'.partial');partial.write_text(json.dumps(value,indent=2,allow_nan=False));partial.replace(path)


def comparisons(baseline: dict[str, Any], scores: list[dict[str, Any]], labels: dict[str, Any]) -> list[dict[str, Any]]:
    if labels['experiment_id']!=baseline['experiment_id']:raise ValueError('Human labels belong to another experiment')
    if len(scores)!=len(baseline['images']):raise ValueError('Incomplete scoring')
    for i,(image,s) in enumerate(zip(baseline['images'],scores)):
        if s['index']!=i or s['path']!=image['path']:raise ValueError('Score identity mismatch')
        if s.get('status','ok')=='ok' and not math.isfinite(s['score']):raise ValueError('Non-finite score')
    output=[]
    for g in baseline['comparisons']:
        ordered=sorted((i for i in g['members'] if scores[i].get('status','ok')=='ok'),key=lambda i:(-scores[i]['score'],i))
        human=labels['answers'].get(g['id'],{});human=human.get('blind_choice',human.get('choice'))
        if human not in (None,'none') and human not in g['members']:raise ValueError('Invalid human member')
        tied=len(ordered)>1 and scores[ordered[0]]['score']==scores[ordered[1]]['score']
        output.append({'group':g['id'],'members':g['members'],'ranking':ordered,'raw_top':ordered[0] if ordered else None,
             'suggested_leader':None if not ordered or tied or g['weak'] or g['chained'] or len(ordered)!=len(g['members']) else ordered[0],
             'exact_tie':tied,'gap':scores[ordered[0]]['score']-scores[ordered[1]]['score'] if len(ordered)>1 else None,
             'human':human,'apple_top':g['ranking_a'][0], 'weak_or_chained':g['weak'] or g['chained'],
             'schuhmann_agrees':human==ordered[0] if isinstance(human,int) and ordered else None,
             'schuhmann_top2_agrees':human in ordered[:2] if isinstance(human,int) else None,
             'apple_agrees':human==g['ranking_a'][0] if isinstance(human,int) else None})
    return output


def report(baseline: dict[str, Any], scores: list[dict[str, Any]], groups: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    esc=html.escape;rows=[];sections=[]
    def name(i: Any) -> str:
        return 'No clear preference' if i=='none' else 'Unselected' if i is None else Path(baseline['images'][i]['path']).name
    for g in groups:
        gap_text=format(g['gap'],'.5f') if g['gap'] is not None else 'Unavailable'
        rows.append(f'<tr><td>{g["group"]}</td><td>{esc(name(g["human"]))}</td><td>{esc(name(g["apple_top"]))}</td><td>{esc(name(g["raw_top"]))}</td><td>{gap_text}</td></tr>')
        if not g['ranking']:
            sections.append(f'<section><h2>{g["group"]}</h2><p>Original files unavailable; no model ranking.</p></section>');continue
        chosen=[]
        for i in (g['human'],g['apple_top'],g['raw_top']):
            if isinstance(i,int) and i not in chosen and scores[i].get('status','ok')=='ok':chosen.append(i)
        cards=[]
        for i in chosen:
            im=baseline['images'][i];s=scores[i];roles=[]
            if i==g['human']:roles.append('Human choice')
            if i==g['apple_top']:roles.append('Apple aesthetic top')
            if i==g['raw_top']:roles.append('Schuhmann raw top')
            cards.append(f'<article><h3>{" · ".join(roles)}</h3><a href="{esc(Path(im["path"]).as_uri(),quote=True)}"><img class="full" src="data:image/jpeg;base64,{im["aesthetics"]["preview"]}" alt="{esc(name(i),quote=True)}"></a><p>{esc(name(i))}</p><p>Apple: {im["aesthetics"]["overallScore"]:.6f} · Schuhmann: {s["score"]:.5f}</p><details><summary>Actual 224×224 model view</summary><img class="crop" src="data:image/png;base64,{s["crop_preview"]}" alt="Actual center crop seen by model"></details></article>')
        sections.append(f'<section><h2>{g["group"]}</h2><p>{"Weak/missing pair evidence: raw ranking only; single-winner recommendation withheld." if g["weak_or_chained"] else "Model ranking is advisory, not a personal winner."}</p><div class="cards">{"".join(cards)}</div><details><summary>All native model scores in this group</summary><ol>'+''.join(f'<li>{esc(name(i))}: {scores[i]["score"]:.5f}</li>' for i in g['ranking'])+'</ol></details></section>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Schuhmann, Apple and human comparison</title><style>body{font:16px system-ui;margin:24px;background:#f4f3ef;color:#222}table{border-collapse:collapse;background:white;width:100%}td,th{padding:10px;border:1px solid #ddd;text-align:left}section{background:white;margin:24px 0;padding:20px}.cards{display:flex;flex-wrap:wrap;gap:18px}article{flex:1 1 340px;max-width:600px}.full{width:100%;height:400px;object-fit:contain;background:#eee}.crop{width:224px;height:224px}p{line-height:1.5}</style><h1>Human, Apple and Schuhmann</h1><p>Original photographs and existing Apple scores remain unchanged. Human choices use the latest recorded review. This is a retrospective comparison on a repeatedly viewed sample set. Scores are different scales and are not averaged. Expand the model-view panels to inspect what center cropping removed.</p><p>'+esc(json.dumps(summary))+'</p><table><tr><th>Group</th><th>Human</th><th>Apple raw top</th><th>Schuhmann raw top</th><th>Schuhmann gap</th></tr>'+''.join(rows)+'</table>'+''.join(sections)+'</html>'


def run(a: argparse.Namespace) -> None:
    # Imports stay here so analysis/unit tests work in the untouched project venv.
    import torch
    import clip
    from torch import nn
    from PIL import Image
    import numpy as np
    start=time.monotonic();baseline=json.loads(a.results.read_text());labels=json.loads(a.labels.read_text())
    if labels['experiment_id']!=baseline['experiment_id']:raise ValueError('Wrong labels')
    paths=[Path(im['path']) for im in baseline['images']];hashes=[im['sha256'] for im in baseline['images']]
    available=[i for i,p in enumerate(paths) if p.is_file()]
    if any(digest(paths[i])!=hashes[i] for i in available):raise ValueError('Source content changed')
    repo=Path(__file__).resolve().parents[3];out=a.output_dir.resolve()
    if out==repo or repo in out.parents:raise ValueError('Private artifacts must stay outside repository')
    out.mkdir(parents=True,exist_ok=False)
    save(out/'run.json',{'status':'running','baseline_experiment':baseline['experiment_id']})
    try:
        # Official locally cached checkpoint; no URL or auto-download is used here.
        loaded,preprocess=clip.load(str(a.clip_weights),device='cpu',jit=False)
        vision=loaded.visual.float().eval();del loaded
        class Predictor(nn.Module):
            def __init__(self):
                super().__init__()
                self.layers=nn.Sequential(nn.Linear(768,1024),nn.Dropout(.2),nn.Linear(1024,128),nn.Dropout(.2),nn.Linear(128,64),nn.Dropout(.1),nn.Linear(64,16),nn.Linear(16,1))
            def forward(self,x):return self.layers(x)
        head=Predictor().float().eval();head.load_state_dict(torch.load(a.head_weights,map_location='cpu',weights_only=True),strict=True)
        def decode(index: int,work: Path):
            image_path=work/'upright.png'
            response=subprocess.run([str(a.decoder),str(paths[index]),str(image_path)],capture_output=True,text=True,check=True,timeout=60)
            geometry=json.loads(response.stdout)
            with Image.open(image_path) as image:
                tensor=preprocess(image.convert('RGB')).unsqueeze(0)
            image_path.unlink()
            return tensor,geometry
        def predict(tensor,device):
            with torch.inference_mode():
                features=vision(tensor.to(device)).float();features=features/features.norm(dim=-1,keepdim=True)
                value=head(features).item()
            if not math.isfinite(value):raise ValueError('Invalid model output')
            return value
        pilots=sorted({0,len(paths)//2,len(paths)-1});pilot=[]
        with tempfile.TemporaryDirectory(prefix='schuhmann-input-') as temp:
            work=Path(temp)
            pilot_tensors=[]
            for index in pilots:
                tensor,geometry=decode(index,work);pilot_tensors.append(tensor)
                pilot.append({'index':index,'cpu_score':predict(tensor,'cpu')})
            device='cpu';mps_error=None
            if torch.backends.mps.is_available():
                try:
                    vision.to('mps');head.to('mps')
                    for record,tensor in zip(pilot,pilot_tensors):
                        record['mps_score']=predict(tensor,'mps');record['absolute_delta']=abs(record['mps_score']-record['cpu_score'])
                    if max(p['absolute_delta'] for p in pilot)>1e-3:raise ValueError('CPU/MPS numerical difference exceeds fixed 0.001 verification tolerance')
                    device='mps'
                except Exception as exc:
                    mps_error=str(exc);vision.to('cpu');head.to('cpu');torch.mps.empty_cache()
            save(out/'device-check.json',{'device':device,'pilot':pilot,'mps_available':torch.backends.mps.is_available(),'mps_error':mps_error,'tolerance':.001,'note':'Numerical engineering tolerance, not a recommendation-confidence threshold.'})
            scores=[];inference_start=time.monotonic()
            for index in range(len(paths)):
                if index not in available:
                    scores.append({'index':index,'path':str(paths[index]),'sha256':hashes[index],'status':'missing','score':None});continue
                image_start=time.monotonic();tensor,geometry=decode(index,work);value=predict(tensor,device)
                # Show the actual preprocessed tensor, undoing only normalization.
                pixels=(tensor[0]*torch.tensor([.26862954,.26130258,.27577711])[:,None,None]+torch.tensor([.48145466,.4578275,.40821073])[:,None,None]).clamp(0,1)
                array=(pixels.permute(1,2,0).numpy()*255).round().astype(np.uint8)
                preview=io.BytesIO();Image.fromarray(array).save(preview,format='PNG')
                scores.append({'index':index,'path':str(paths[index]),'sha256':hashes[index],'status':'ok','score':value,'geometry':geometry,
                     'crop_preview':base64.b64encode(preview.getvalue()).decode(),'seconds':time.monotonic()-image_start})
                save(out/'scores.partial.json',scores);print(f'Schuhmann {index+1}/{len(paths)}',flush=True)
            # Repeat the first sample on the selected device after the batch.
            repeat=predict(pilot_tensors[0],device)
            repeat_delta=abs(repeat-scores[pilots[0]]['score'])
        groups=comparisons(baseline,scores,labels);specific=[g for g in groups if isinstance(g['human'],int) and g['schuhmann_agrees'] is not None]
        summary={'images':len(available),'missing_images':len(paths)-len(available),'groups':sum(bool(g['ranking']) for g in groups),'unavailable_groups':sum(not g['ranking'] for g in groups),'human_image_choices':len(specific),'human_no_preference':sum(g['human']=='none' for g in groups),
                 'schuhmann_top1':sum(g['schuhmann_agrees'] for g in specific),'schuhmann_top2':sum(g['schuhmann_top2_agrees'] for g in specific),
                 'apple_top1':sum(g['apple_agrees'] for g in specific),'model_top_agreement':sum(g['raw_top']==g['apple_top'] for g in groups),
                 'device':device,'batch_seconds':time.monotonic()-inference_start,'total_seconds':time.monotonic()-start,'repeat_score_delta':repeat_delta}
        if any(digest(paths[i])!=hashes[i] for i in available):raise ValueError('Source changed during scoring')
        provenance={'python':platform.python_version(),'os':platform.platform(),'packages':{p:importlib.metadata.version(p) for p in ('torch','torchvision','pillow','clip')},
            'clip_weights_sha256':digest(a.clip_weights),'head_weights_sha256':digest(a.head_weights),'decoder_sha256':digest(a.decoder),
            'implementation_sha256':digest(Path(__file__)),'python_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'input':'Original file → full-size orientation-corrected ImageIO sRGB PNG → official CLIP resize/center-crop/normalize (224×224)',
            'model':'CLIP ViT-L/14 visual encoder + sac+logos+ava1-l14-linearMSE.pth; 768 normalized features, original linear layers/dropout, float32 eval',
            'source_checksums_unchanged':True,'network':'No downloads or external calls during private-image inference; weights supplied as local paths.'}
        save(out/'results.json',{'summary':summary,'provenance':provenance,'scores':scores,'groups':groups})
        (out/'comparison.html').write_text(report(baseline,scores,groups,summary))
        save(out/'run.json',{'status':'complete','summary':summary});print(json.dumps(summary))
    except BaseException as exc:
        save(out/'run.json',{'status':'interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed','error':str(exc)});raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('results','labels','clip-weights','head-weights','decoder','output-dir'):parser.add_argument('--'+name,type=Path,required=True)
    run(parser.parse_args())
