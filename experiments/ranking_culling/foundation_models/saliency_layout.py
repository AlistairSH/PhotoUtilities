"""Cached saliency geometry: measurable anchor distances, no composition verdict."""
from __future__ import annotations
import argparse, html, json, math
from pathlib import Path

def geometry(box,width,height):
    if len(box)!=4 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in box):raise ValueError('Invalid box')
    x,y,w,h=box
    if w<=0 or h<=0 or width<=0 or height<=0:raise ValueError('Invalid geometry')
    left=max(0,min(1,x));top=max(0,min(1,y));right=max(0,min(1,x+w));bottom=max(0,min(1,y+h))
    if right<=left or bottom<=top:raise ValueError('Box outside image')
    cx=(left+right)/2;cy=(top+bottom)/2;diagonal=math.hypot(width,height)
    def distance(px,py):return math.hypot((cx-px)*width,(cy-py)*height)/diagonal
    thirds=[(a,b) for a in (1/3,2/3) for b in (1/3,2/3)];nearest=min(thirds,key=lambda point:distance(*point))
    return {'visible_box':[left,top,right-left,bottom-top],'clipped_to_frame':list(box)!=[left,top,right-left,bottom-top],
        'center':[cx,cy],'visible_area_fraction':(right-left)*(bottom-top),
        'distance_to_center_diagonal_fraction':distance(.5,.5),'distance_to_nearest_thirds_diagonal_fraction':distance(*nearest),
        'nearest_thirds_intersection':list(nearest),'nearest_edge_margin_frame_fraction':min(left,top,1-right,1-bottom)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--vision',type=Path,required=True);p.add_argument('--exposure',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):raise ValueError('Private outputs must remain outside Git')
    result=json.loads(a.results.read_text());vision=json.loads(a.vision.read_text());native={(r['id'],r['max_dimension']):r for r in vision['rows'] if r.get('status')=='ok'}
    exposure={}
    if a.exposure:exposure={r['id']:r for r in json.loads(a.exposure.read_text())['rows']}
    rows=[]
    for image in result['images']:
        row={'id':image['id'],'group':image['group'],'kind':image['kind'],'scales':{},'exposure':exposure.get(image['id'])};rows.append(row)
        for size in (1024,2048):
            source=native[(image['id'],size)]
            if source['path']!=image['path']:raise ValueError('Native identity mismatch')
            detectors={}
            for name in ('attention','objectness'):
                request=source['requests'][name]
                if request['status']!='ok':detectors[name]={'status':'failed','objects':[],'primary_index':None};continue
                objects=[dict(index=i,box=o['box'],geometry=geometry(o['box'],source['width'],source['height'])) for i,o in enumerate(request['observations'])]
                primary=max(objects,key=lambda o:o['geometry']['visible_area_fraction'])['index'] if objects else None
                detectors[name]={'status':'ok','objects':objects,'primary_index':primary}
            row['scales'][str(size)]=detectors
    rankings={}
    for gid in sorted({r['group'] for r in rows if r['group']}):
        members=[r for r in rows if r['group']==gid];rankings[gid]={}
        for name in ('attention','objectness'):
            for anchor,key in [('center','distance_to_center_diagonal_fraction'),('thirds','distance_to_nearest_thirds_diagonal_fraction')]:
                measured=[]
                for r in members:
                    d=r['scales']['2048'][name]
                    if d['primary_index'] is not None:
                        g=next(o['geometry'] for o in d['objects'] if o['index']==d['primary_index']);measured.append({'id':r['id'],'distance':g[key]})
                rankings[gid][name+'_'+anchor]=sorted(measured,key=lambda x:x['distance'])
    a.output.mkdir(exist_ok=False,parents=True)
    (a.output/'results.json').write_text(json.dumps({'primary_selection':'Largest visible box per detector, a provisional geometry convention, not verified subject identity.','distance_units':'Pixel distance divided by image diagonal, preserving aspect ratio.','automatic_cull_flags':False,'rows':rows,'group_anchor_rankings_2048':rankings},indent=2))
    images={i['id']:i for i in result['images']};sections=[]
    for gid in sorted({r['group'] or 'Solo images' for r in rows}):
        cards=[]
        for row in rows:
            if (row['group'] or 'Solo images')!=gid:continue
            image=images[row['id']];boxes='';lines='';details=[]
            for name,color in [('attention','#e64dbb'),('objectness','#13a4c8')]:
                d=row['scales']['1024'][name]
                for o in d['objects']:
                    g=o['geometry'];x,y,w,h=g['visible_box'];cx,cy=g['center'];primary=o['index']==d['primary_index']
                    boxes+=f'<rect x="{x*100}" y="{y*100}" width="{w*100}" height="{h*100}" fill="none" stroke="{color}" stroke-width="{.6 if primary else .25}"/><circle cx="{cx*100}" cy="{cy*100}" r=".7" fill="{color}"/>'
                p_obj=next((o for o in d['objects'] if o['index']==d['primary_index']),None)
                if p_obj:
                    g=p_obj['geometry'];details.append(f'{name}: center distance {g["distance_to_center_diagonal_fraction"]:.4f}; thirds distance {g["distance_to_nearest_thirds_diagonal_fraction"]:.4f}')
                else:details.append(name+': no measured box')
            for point in (100/3,200/3):lines+=f'<line x1="{point}" y1="0" x2="{point}" y2="100" stroke="white" stroke-width=".2"/><line x1="0" y1="{point}" x2="100" y2="{point}" stroke="white" stroke-width=".2"/>'
            lines+='<circle cx="50" cy="50" r=".8" fill="yellow"/>'
            exp=row.get('exposure');exp_text=''
            if exp:
                g=exp['global'];exp_text=f'<p>Near-white frame: {g["near_white_all_channels_percent"]:.2f}%; near-black frame: {g["near_black_all_channels_percent"]:.2f}%</p>'
            cards.append(f'<article><h3>{row["id"]}</h3><div class="picture"><img src="data:image/jpeg;base64,{image["thumbnail"]}" alt="Local photograph"><svg viewBox="0 0 100 100" preserveAspectRatio="none">{lines}{boxes}</svg></div><p>'+html.escape('; '.join(details))+exp_text+'</p><details><summary>Both scales, all objects and exposure regions</summary><pre>'+html.escape(json.dumps(row,indent=2))+'</pre></details></article>')
        sections.append('<section><h2>'+html.escape(gid)+'</h2><div class="cards">'+''.join(cards)+'</div></section>')
    (a.output/'review.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Saliency location and exposure review</title><style>body{font:16px system-ui;margin:24px;background:#f4f3ef}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px}article{padding:16px;background:white}.picture{position:relative}img{display:block;width:100%}svg{position:absolute;inset:0;width:100%;height:100%}pre{white-space:pre-wrap}</style><h1>Saliency location and exposure</h1><p>Magenta: attention. Cyan: objectness. Dots: box centers. White: thirds grid. Yellow: frame center. Thick boxes are the largest visible box from each detector. Smaller anchor distance is closer, not automatically better composition. Displayed overlays use 1024; saved rankings use 2048. Exposure is measured on the exact 8-bit 1024 display view.</p>'+''.join(sections))
    different=0;comparable=0
    for g,ranks in rankings.items():
        lists=[tuple(v['id'] for v in ranks[k]) for k in ('attention_center','attention_thirds')]
        if len(lists[0])>1 and set(lists[0])==set(lists[1]):comparable+=1;different+=lists[0]!=lists[1]
    print(json.dumps({'images':len(rows),'groups':len(rankings),'attention_anchor_comparisons':comparable,'different_center_vs_thirds_orders':different},indent=2))
if __name__=='__main__':main()
