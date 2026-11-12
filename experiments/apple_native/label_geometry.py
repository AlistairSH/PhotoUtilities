"""Bind explicit human grouping labels to a frozen geometry evaluation.
Uncertain/unjudged choices are excluded from binary agreement counts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def bind_labels(summary_bytes, labels):
    digest = hashlib.sha256(summary_bytes).hexdigest()
    if labels.get('binding', {}).get('summary_sha256') != digest:
        raise ValueError('Labels do not belong to this exact evaluation')
    summary = json.loads(summary_bytes)
    controls = {r['case']: r for r in summary['rows']
                if r['mode'] == 'register-canvas' and r['label'] == 'unjudged'}
    if not controls:
        raise ValueError('No unjudged corpus controls in evaluation')
    rows = labels.get('rows')
    if not isinstance(rows, list):
        raise ValueError('Missing label rows')
    choices = {}
    for row in rows:
        case, label = row.get('case'), row.get('label')
        if case not in controls or case in choices:
            raise ValueError('Unknown or duplicate case')
        if label not in ('related', 'unrelated', 'uncertain', 'unjudged'):
            raise ValueError('Unsupported label')
        choices[case] = label
    if set(choices) != set(controls):
        raise ValueError('Missing control labels; provide explicit unjudged choices')
    joined = []
    for case, evidence in controls.items():
        pair = evidence['baseline_pair']
        label = choices[case]
        judged = label in ('related', 'unrelated')
        baseline = pair['baseline_level'] != 'unmatched'
        vision = pair['vision_only_level'] != 'unmatched'
        joined.append({'case': case, 'human_label': label, 'included_in_binary_counts': judged,
                       'accepted_related': baseline, 'vision_only_related': vision,
                       'sift_candidate': evidence['sift']['sift_candidate'],
                       'accepted_agrees': baseline == (label == 'related') if judged else None,
                       'vision_only_agrees': vision == (label == 'related') if judged else None,
                       'native_confidence': evidence['evidence'].get('confidence'),
                       'native_overlap_ncc': evidence['diagnostics'].get('overlap_ncc')})
    judged = [r for r in joined if r['included_in_binary_counts']]
    return {'evaluation_sha256': digest, 'label_counts': dict(Counter(choices.values())),
            'judged_pairs': len(judged),
            'accepted_agrees': sum(r['accepted_agrees'] for r in judged),
            'vision_only_agrees': sum(r['vision_only_agrees'] for r in judged),
            'human_confirmed_sift_only': [r['case'] for r in joined
                                         if r['human_label'] == 'related' and r['accepted_related']
                                         and not r['vision_only_related']],
            'rows': joined,
            'scope': 'Selected development controls only; not held-out accuracy. Native registration has no match classifier. Uncertain/unjudged remain excluded.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels', type=Path)
    parser.add_argument('--evaluation', type=Path, required=True, help='Frozen summary.json')
    parser.add_argument('--output', type=Path, required=True, help='New private output directory')
    args = parser.parse_args()
    label_bytes = args.labels.read_bytes()
    evaluation_bytes = args.evaluation.read_bytes()
    result = bind_labels(evaluation_bytes, json.loads(label_bytes))
    result['labels_sha256'] = hashlib.sha256(label_bytes).hexdigest()
    if args.labels.read_bytes() != label_bytes or args.evaluation.read_bytes() != evaluation_bytes:
        raise RuntimeError('Input changed during analysis')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    args.output.chmod(0o700)
    (args.output/'human-labels.json').write_bytes(label_bytes)
    (args.output/'label-analysis.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
