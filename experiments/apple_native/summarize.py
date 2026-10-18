"""Print aggregate comparison statistics without publishing photo identities."""
import argparse
import json
from pathlib import Path
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('result',type=Path)
args = parser.parse_args()
summary = json.loads((args.result/'summary.json').read_text())
focus = json.loads((args.result/'focus.json').read_text())
result = {k:v for k,v in summary.items() if k not in ('baseline_components','native_components','native_binary_sha256')}
for key in ('baseline_components','native_components'):
    result[key+'_groups'] = sum(len(g)>1 for g in summary[key])
    result[key+'_singles'] = sum(len(g)==1 for g in summary[key])
if focus:
    result['focus_relative_error_median'] = {key:float(np.median([r['relative_error'][key] for r in focus])) for key in focus[0]['relative_error']}
    agreement = {}
    for scale in (1024,2048):
        rows = [r for r in focus if r['scale']==scale]
        for metric in ('laplacian_variance','tenengrad'):
            total = flipped = 0
            for i,a in enumerate(rows):
                for b in rows[i+1:]:
                    x = np.sign(a['native'][metric]-b['native'][metric])
                    y = np.sign(a['baseline'][metric]-b['baseline'][metric])
                    total += 1; flipped += x!=y
            agreement[f'{scale}/{metric}'] = {'comparisons':total,'order_differences':int(flipped)}
    result['global_metric_order_agreement'] = agreement
    differences = []
    for row in focus:
        regions = row.get('regions')
        if not regions:
            continue
        for a,b in zip(regions['native']['regions'],regions['baseline']['regions']):
            if a['id']!=b['id'] or a['usable']!=b['usable']:
                raise ValueError('Regional identity or usability mismatch')
            if not a['smoothed'] or not b['smoothed']:
                continue
            for domain in ('region','outside','region_to_outside'):
                av,bv = a['smoothed'][domain],b['smoothed'][domain]
                if (av is None)!=(bv is None):
                    raise ValueError('Regional missing-value disagreement')
                if av and bv:
                    for key in ('laplacian_variance','tenengrad','gradient_energy_p90'):
                        if av.get(key) is not None and bv.get(key) is not None:
                            differences.append(abs(av[key]-bv[key])/max(abs(bv[key]),1e-12))
    if differences:
        result['regional_scalar_relative_error'] = {'measurements':len(differences),'median':float(np.median(differences)),'max':max(differences)}
print(json.dumps(result,indent=2))
