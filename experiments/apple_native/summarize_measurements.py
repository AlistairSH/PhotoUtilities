"""Read-only numeric diagnostics for a completed decision-parity replay."""
import argparse
import json
from pathlib import Path


def summarize(fixture,run):
    baseline=json.loads((fixture/'baseline.json').read_text())['focus_rows']
    native=[json.loads(line) for line in (run/'measurements.jsonl').read_text().splitlines()]
    complete=native.pop()
    if complete.get('type')!='complete' or len(native)!=len(baseline):
        raise RuntimeError('Incomplete replay')
    for a,b in zip(baseline,native):
        if (a['path'],a['max_dimension'])!=(b['path'],b['max_dimension']):
            raise RuntimeError('Mismatched replay identity')
    result={'scale_rows':len(native),
        'exposure_exact_matches':sum(a['exposure']==b['exposure'] for a,b in zip(baseline,native) if 'exposure' in a),
        'global_edge_count_differences':sum(a['edge_global']['edges']!=b['edge_global']['edges'] for a,b in zip(baseline,native)),
        'regional_sufficiency_differences':sum(a['metrics']['sufficient']!=b['metrics']['sufficient'] for x,y in zip(baseline,native) for a,b in zip(x['edge_regions'],y['edge_regions'])),
        'regional_mask_pixel_differences':sum(a['smoothed'][domain]['pixels']!=b['smoothed'][domain]['pixels'] for x,y in zip(baseline,native) for a,b in zip(x['focus']['regions'],y['focus']['regions']) if a['smoothed'] and b['smoothed'] for domain in ('region','outside') if a['smoothed'][domain] and b['smoothed'][domain])}
    for key in ('laplacian_variance','tenengrad'):
        values=[(a['focus']['global']['smoothed'][key],b['focus']['global']['smoothed'][key]) for a,b in zip(baseline,native)]
        result[key]={'max_absolute_error':max(abs(a-b) for a,b in values),'max_relative_error':max(abs(a-b)/max(abs(a),1e-12) for a,b in values)}
    for key in ('median_width','contrast_soft_fraction'):
        result['edge_'+key+'_max_abs_error']=max(abs(a['edge_global'][key]-b['edge_global'][key]) for a,b in zip(baseline,native) if a['edge_global'].get(key) is not None and b['edge_global'].get(key) is not None)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture',type=Path);parser.add_argument('run',type=Path)
    args=parser.parse_args()
    print(json.dumps(summarize(args.fixture,args.run),indent=2))
