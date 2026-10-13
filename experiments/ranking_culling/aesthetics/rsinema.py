"""Offline seven-component rsinema test and diagnostic comparison charts."""
from __future__ import annotations
import argparse
import base64
import html
import io
import json
import math
import os
import platform
import resource
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from schuhmann import digest,save

AXES=('Overall','Technical quality','Composition','Lighting','Color harmony','Depth of field','Content')
HEADS=('aesthetic','quality','composition','light','color','dof','content')


def validate_values(values: list[float]) -> None:
    if len(values)!=7 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in values):raise ValueError('Expected seven finite numeric components')


def compare(baseline: dict[str, Any], scores: list[dict[str, Any]], labels: dict[str, Any], schuhmann: dict[str, Any]) -> list[dict[str, Any]]:
    if baseline['experiment_id']!=labels['experiment_id']:raise ValueError('Human labels experiment mismatch')
    if len(scores)!=len(baseline['images']):raise ValueError('Incomplete component rows')
    for i,(row,image) in enumerate(zip(scores,baseline['images'])):
        if row['index']!=i or row['path']!=image['path']:raise ValueError('Component identity mismatch')
        if row['status']=='ok':validate_values(row['values'])
    previous={g['group']:g for g in schuhmann['groups']};groups=[]
    for original in baseline['comparisons']:
        gid=original['id'];members=original['members'];eligible=[i for i in members if scores[i]['status']=='ok']
        rankings=[sorted(eligible,key=lambda i:(-scores[i]['values'][axis],i)) for axis in range(7)]
        answer=labels['answers'].get(gid,{});human=answer.get('blind_choice',answer.get('choice'))
        if human not in (None,'none') and human not in members:raise ValueError('Invalid human choice')
        picks={}
        for role,index in [('Human',human),('Apple',original['ranking_a'][0]),('Schuhmann',previous[gid]['raw_top'])]:
            if isinstance(index,int) and index in eligible:picks.setdefault(index,[]).append(role)
        groups.append({'group':gid,'members':members,'apple_order':[i for i in original['ranking_a'] if i in eligible],
             'rankings':rankings,'overall_top':rankings[0][0] if eligible else None,'human':human,
             'apple_top':original['ranking_a'][0],'schuhmann_top':previous[gid]['raw_top'],
             'picks':[{'index':i,'roles':roles} for i,roles in picks.items()],
             'partial':len(eligible)!=len(members),'weak_or_chained':original['weak'] or original['chained']})
    return groups


def charts(groups: list[dict[str, Any]], scores: list[dict[str, Any]], directory: Path) -> dict[str,str]:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    directory.mkdir()
    images={};angles=np.linspace(0,2*np.pi,7,endpoint=False).tolist();angles+=angles[:1]
    for group in groups:
        if not group['picks']:continue
        fig,ax=plt.subplots(figsize=(8,7),subplot_kw={'projection':'polar'})
        ax.set_theta_offset(np.pi/2);ax.set_theta_direction(-1)
        ax.set_xticks(angles[:-1],['Overall','Technical\nquality','Composition','Lighting','Color\nharmony','Depth of\nfield','Content'])
        ax.set_ylim(0,5);ax.set_yticks([1,2,3,4,5]);ax.set_rlabel_position(12)
        ax.tick_params(axis='x',pad=15);ax.grid(alpha=.4)
        for pick,color in zip(group['picks'],('#2563eb','#e87913','#16a34a')):
            row=scores[pick['index']];values=row['values'];label=' + '.join(pick['roles'])+' · '+Path(row['path']).name
            ax.plot(angles,values+values[:1],color=color,linewidth=2,label=label);ax.fill(angles,values+values[:1],color=color,alpha=.06)
        ax.set_title(group['group']+' · predicted rsinema components',pad=28)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.12),frameon=False,fontsize=9)
        fig.subplots_adjust(top=.85,bottom=.22,left=.12,right=.88)
        stream=io.BytesIO();fig.savefig(stream,format='png',dpi=140,facecolor='white');plt.close(fig)
        data=stream.getvalue();(directory/(group['group']+'.png')).write_bytes(data)
        images[group['group']]=base64.b64encode(data).decode()
    return images


def render(baseline: dict[str, Any], scores: list[dict[str, Any]], groups: list[dict[str, Any]], summary: dict[str, Any], chart_images: dict[str,str]) -> str:
    esc=html.escape;sections=[]
    for g in groups:
        if not g['apple_order']:
            sections.append(f'<section><h2>{g["group"]}</h2><p>Original files unavailable.</p></section>');continue
        picks=[]
        for pick in g['picks']:
            i=pick['index'];im=baseline['images'][i]
            picks.append(f'<article><h3>{" + ".join(pick["roles"])}</h3><a href="{esc(Path(im["path"]).as_uri(),quote=True)}"><img src="data:image/jpeg;base64,{im["aesthetics"]["preview"]}" alt="{esc(Path(im["path"]).name,quote=True)}"></a><p>{esc(Path(im["path"]).name)}</p><details><summary>Actual rsinema model view</summary><img class="crop" src="data:image/png;base64,{scores[i]["crop_preview"]}"></details></article>')
        table=[]
        for i in g['apple_order']:
            roles=next((p['roles'] for p in g['picks'] if p['index']==i),[])
            table.append('<tr><td>'+esc(Path(scores[i]['path']).name)+'<br>'+esc(' + '.join(roles))+'</td>'+''.join(f'<td>{v:.3f}</td>' for v in scores[i]['values'])+'</tr>')
        chart=f'<details><summary>Show radar chart for the human / Apple / Schuhmann picks</summary><p>All axes are rsinema predictions on the same 0–5 scale. Area is not an overall winner. Matching picks share one polygon.</p><img class="radar" src="data:image/png;base64,{chart_images[g["group"]]}" alt="Seven component comparison"></details>' if g['group'] in chart_images else ''
        overall=g['overall_top'];top_name=Path(scores[overall]['path']).name if overall is not None else 'Unavailable'
        sections.append(f'<section><h2>{g["group"]}</h2><p>Raw rsinema overall top: {esc(top_name)}. {"Human: no clear preference." if g["human"]=="none" else ""}</p><div class="cards">{"".join(picks)}</div>{chart}<div class="scroll"><table><tr><th>Image · rows ordered by Apple aesthetic score</th>'+''.join('<th>'+esc(a)+'</th>' for a in AXES)+'</tr>'+''.join(table)+'</table></div></section>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>rsinema component experiment</title><style>body{font:16px system-ui;margin:24px;background:#f4f3ef;color:#222}section{background:white;padding:20px;margin:24px 0}.cards{display:flex;flex-wrap:wrap;gap:18px}article{flex:1 1 330px;max-width:600px}article img{width:100%;height:360px;object-fit:contain;background:#eee}article .crop{width:224px;height:224px}.radar{width:100%;max-width:850px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;margin-top:20px}td,th{padding:9px;border:1px solid #ddd;text-align:left}details{padding:12px;border:1px solid #ddd;margin:12px 0}summary{cursor:pointer;font-weight:600}p{line-height:1.5}</style><h1>rsinema: seven predicted components</h1><p>Diagnostic trial only. Existing human choices, Apple and Schuhmann rankings are reused. The chart compares rsinema predictions for those picked images; it does not explain either other model’s reasoning. Component labels and scale come from the model author and are not independently calibrated by this experiment.</p><p>'+esc(json.dumps(summary))+'</p>'+''.join(sections)+'</html>'


def run(a: argparse.Namespace) -> None:
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    import torch
    from torch import nn
    import numpy as np
    from PIL import Image
    from transformers import CLIPVisionConfig,CLIPVisionModel,CLIPImageProcessor
    import importlib.metadata
    start=time.monotonic();baseline=json.loads(a.results.read_text());labels=json.loads(a.labels.read_text());previous=json.loads(a.schuhmann.read_text())
    paths=[Path(im['path']) for im in baseline['images']];expected=[im['sha256'] for im in baseline['images']]
    available=[i for i,p in enumerate(paths) if p.is_file()]
    if any(digest(paths[i])!=expected[i] for i in available):raise ValueError('Source changed')
    repo=Path(__file__).resolve().parents[3];out=a.output_dir.resolve()
    if out==repo or repo in out.parents:raise ValueError('Private artifacts must remain outside repository')
    out.mkdir(parents=True,exist_ok=False);os.environ['MPLCONFIGDIR']=str(out/'plot-cache')
    save(out/'run.json',{'status':'running'})
    try:
        config=CLIPVisionConfig(hidden_size=768,intermediate_size=3072,num_hidden_layers=12,num_attention_heads=12,
             image_size=224,patch_size=32,hidden_act='quick_gelu',layer_norm_eps=1e-5)
        class Scorer(nn.Module):
            def __init__(self):
                super().__init__();vision=CLIPVisionModel(config);self.backbone=getattr(vision,'vision_model',vision)
                for name in HEADS:setattr(self,name+'_head',nn.Sequential(nn.Linear(768,1)))
            def forward(self,x):
                features=self.backbone(x).pooler_output
                return torch.cat([getattr(self,n+'_head')(features) for n in HEADS],dim=-1)
        model=Scorer().float().eval();state=torch.load(a.model_dir/'model.pt',map_location='cpu',weights_only=True)
        model.load_state_dict(state,strict=True);del state
        processor=CLIPImageProcessor.from_pretrained(a.model_dir,local_files_only=True)
        save(out/'vision-config.json',config.to_dict())
        def decode(index,work):
            p=work/'upright.png';response=subprocess.run([str(a.decoder),str(paths[index]),str(p)],capture_output=True,text=True,check=True,timeout=60)
            with Image.open(p) as image:values=processor(images=image.convert('RGB'),return_tensors='pt')['pixel_values']
            p.unlink();return values,json.loads(response.stdout)
        def predict(tensor,device):
            with torch.inference_mode():values=model(tensor.to(device)).cpu()[0].tolist()
            validate_values(values);return values
        with tempfile.TemporaryDirectory(prefix='rsinema-input-') as temp:
            work=Path(temp);pilots=sorted({available[0],available[len(available)//2],available[-1]});pilot=[];tensors=[]
            for i in pilots:
                tensor,_=decode(i,work);tensors.append(tensor);pilot.append({'index':i,'cpu_values':predict(tensor,'cpu')})
            device='cpu';mps_error=None
            if torch.backends.mps.is_available():
                try:
                    model.to('mps')
                    for record,tensor in zip(pilot,tensors):
                        record['mps_values']=predict(tensor,'mps');record['max_delta']=max(abs(x-y) for x,y in zip(record['cpu_values'],record['mps_values']))
                    if max(p['max_delta'] for p in pilot)>.001:raise ValueError('CPU/MPS difference exceeds fixed numerical tolerance')
                    device='mps'
                except Exception as exc:model.to('cpu');mps_error=str(exc);torch.mps.empty_cache()
            save(out/'device-check.json',{'device':device,'pilot':pilot,'mps_error':mps_error,'tolerance':.001})
            scores=[]
            for i,p in enumerate(paths):
                if i not in available:scores.append({'index':i,'path':str(p),'status':'missing'});continue
                t=time.monotonic();tensor,geometry=decode(i,work);values=predict(tensor,device)
                mean=torch.tensor(processor.image_mean)[:,None,None];std=torch.tensor(processor.image_std)[:,None,None]
                pixels=(tensor[0]*std+mean).clamp(0,1);array=(pixels.permute(1,2,0).numpy()*255).round().astype(np.uint8)
                buf=io.BytesIO();Image.fromarray(array).save(buf,format='PNG')
                scores.append({'index':i,'path':str(p),'sha256':expected[i],'status':'ok','values':values,'geometry':geometry,
                    'crop_preview':base64.b64encode(buf.getvalue()).decode(),'seconds':time.monotonic()-t})
                save(out/'scores.partial.json',scores);print(f'rsinema {len(scores)}/{len(paths)}',flush=True)
            repeat=predict(tensors[0],device);repeat_delta=max(abs(x-y) for x,y in zip(repeat,scores[pilots[0]]['values']))
        groups=compare(baseline,scores,labels,previous);specific=[g for g in groups if isinstance(g['human'],int) and g['overall_top'] is not None]
        values=np.asarray([s['values'] for s in scores if s['status']=='ok'])
        centered=[]
        for g in groups:
            members=g['apple_order']
            if len(members)>1:
                matrix=np.asarray([scores[i]['values'] for i in members]);centered.extend((matrix-matrix.mean(axis=0)).tolist())
        diagnostics={'axis_names':AXES,'ranges':[{'min':float(values[:,i].min()),'max':float(values[:,i].max()),'std':float(values[:,i].std())} for i in range(7)],
            'global_correlations':np.corrcoef(values,rowvar=False).tolist(),'within_group_correlations':np.corrcoef(np.asarray(centered),rowvar=False).tolist(),
            'axis_top1_hits':[sum(g['rankings'][i][0]==g['human'] for g in specific) for i in range(7)]}
        summary={'images':len(available),'groups':sum(bool(g['apple_order']) for g in groups),'missing_images':len(paths)-len(available),
           'human_image_choices':len(specific),'rsinema_top1':sum(g['overall_top']==g['human'] for g in specific),
           'rsinema_top2':sum(g['human'] in g['rankings'][0][:2] for g in specific),'apple_top1':sum(g['apple_top']==g['human'] for g in specific),
           'schuhmann_top1':sum(g['schuhmann_top']==g['human'] for g in specific),'outside_documented_range':int(((values<0)|(values>5)).sum()),
           'device':device,'repeat_max_delta':repeat_delta,'seconds_before_report':time.monotonic()-start}
        if any(digest(paths[i])!=expected[i] for i in available):raise ValueError('Source changed during scoring')
        provenance={'model_sha256':digest(a.model_dir/'model.pt'),'implementation_sha256':digest(Path(__file__)),'python':platform.python_version(),
            'packages':{name:importlib.metadata.version(name) for name in ('torch','transformers','pillow','matplotlib')},
            'source_checksums_unchanged':True,'strict_checkpoint_load':True,'head_order':HEADS,'axes':AXES,'documented_range':[0,5],
            'processor':'Local published config, 224×224 center crop; fresh full-size ImageIO upright sRGB source input',
            'python_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'network':'Offline environment flags, local weights/config only during inference'}
        save(out/'results.json',{'scores':scores,'groups':groups,'summary':summary,'diagnostics':diagnostics,'provenance':provenance})
        chart_images=charts(groups,scores,out/'charts') if not summary['outside_documented_range'] else {}
        (out/'comparison.html').write_text(render(baseline,scores,groups,summary,chart_images))
        save(out/'run.json',{'status':'complete','total_seconds':time.monotonic()-start,'summary':summary})
        print(json.dumps(summary));print('axis top-1',diagnostics['axis_top1_hits'])
    except BaseException as exc:save(out/'run.json',{'status':'interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed','error':str(exc)});raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('results','labels','schuhmann','model-dir','decoder','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
