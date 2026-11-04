"""Compare the live Swift coordinator with a checksum-bound accepted CLI run.
The native application has no Python runtime; this is validation infrastructure.
"""
from __future__ import annotations
import argparse
import json
import math
import subprocess
import time
from pathlib import Path
from freeze_evidence import digest
from policy_compare import expected, differences
from measurement_compare import projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    complete = json.loads((args.fixture/'complete.json').read_text())
    for name, sha in complete['files'].items():
        if digest(args.fixture/name) != sha:
            raise RuntimeError('Changed baseline evidence: '+name)
    inventory = json.loads((args.fixture/'inventory.json').read_text())
    def verify_sources():
        for path, sha in inventory.items():
            if digest(Path(path)) != sha:
                raise RuntimeError('Missing or changed original: '+path)
    verify_sources()
    baseline = json.loads((args.fixture/'baseline.json').read_text())
    if [im['path'] for im in baseline['images']] != list(inventory):
        raise RuntimeError('Baseline identity order differs')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    binary_hash = digest(args.binary)
    command = [str(args.binary.resolve())]
    if not complete['auto_rotate']:
        command.append('--no-auto-rotate')
    started = time.perf_counter()
    with (args.output/'native.json').open('x') as out, (args.output/'native.stderr').open('x') as err:
        process = subprocess.run(['/usr/bin/time', '-l']+command, input=json.dumps(list(inventory)),
                                 text=True, stdout=out, stderr=err, timeout=7200)
    if process.returncode:
        raise RuntimeError('Coordinator failed; see native.stderr')
    actual = json.loads((args.output/'native.json').read_text())
    if [s['input']['id'] for s in actual['sources']] != list(inventory):
        raise RuntimeError('Coordinator identity order differs')
    if any(s['sha256'] != inventory[s['input']['id']] for s in actual['sources']):
        raise RuntimeError('Coordinator source checksum differs')
    if len(actual['photos']) != len(inventory) or len(actual['batch']['focus_rows']) != 2*len(inventory):
        raise RuntimeError('Incomplete coordinator summaries or measurements')
    evidence = [{'a':p['a'],'b':p['b'],'visionDistance':p['vision_distance'],
                 'sift':{'mutualMatches':p['mutual_matches'],'inliers':p['inliers'],
                         'inlierFraction':p['inlier_fraction'],'coverageA':p['coverage_a'],
                         'coverageB':p['coverage_b'],'candidate':p['sift_candidate']}}
                for p in baseline['pairs']]
    evidence_changes = differences(evidence, actual['pairEvidence'])
    keypoint_changes = differences([im['sift_features'] for im in baseline['images']],
                                  [s['siftKeypoints'] for s in actual['sources']])
    changed = differences(projection(expected(baseline)), projection(actual['review']))
    pair_changes = differences([{k:p[k] for k in ('a','b','level')} for p in baseline['pairs']], actual['batch']['pairs'])
    rotations = [im['rotation']['quarter_turns_clockwise'] for im in baseline['images']]
    rotation_changes = differences(rotations, [s['rotation']['quarter_turns_clockwise'] for s in actual['sources']])
    # UI summaries must match both policy decisions and displayed set ordering.
    summary_changes = []
    sets = [g['members'] for g in actual['review']['groups']] + [actual['review']['unmatched']]
    for i,(photo,row) in enumerate(zip(actual['photos'], actual['review']['images'])):
        display = next(s for s in sets if i in s)
        if (photo['sourceID'] != list(inventory)[i] or photo['tier'] != row['tier_review']['tier'] or
            photo['possibleMissedFocus'] != row['focus_review']['review_suggestion'] or
            photo['rankWithinSet'] != display.index(i)+1 or photo['setSize'] != len(display)):
            summary_changes.append(i)
    verify_sources()
    if digest(args.binary) != binary_hash:
        raise RuntimeError('Binary changed during comparison')
    timings = actual.get('timings')
    if not timings or set(timings) != {'validating','analyzing','matching','ranking','verifying','total'} or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v < 0 for v in timings.values()):
        raise RuntimeError('Missing or invalid phase timings')
    if sum(v for k,v in timings.items() if k != 'total') > timings['total'] + 0.01:
        raise RuntimeError('Phase timings exceed total')
    summary = {'timings_seconds':timings, 'images':len(inventory), 'pairs':len(baseline['pairs']),
               'decision_differences':len(changed), 'pair_differences':len(pair_changes),
               'pair_evidence_differences':len(evidence_changes), 'keypoint_differences':len(keypoint_changes),
               'rotation_differences':len(rotation_changes), 'summary_differences':summary_changes,
               'changed_focus_flags':sum(a['focus_review']['review_suggestion'] != b['focus_review']['review_suggestion']
                                         for a,b in zip(baseline['images'],actual['review']['images'])),
               'changed_tiers':sum(a['tier_review']['tier'] != b['tier_review']['tier']
                                   for a,b in zip(baseline['images'],actual['review']['images'])),
               'groups':len(actual['orderedGroups']), 'ungrouped':len(actual['orderedUngrouped']),
               'source_checksums_unchanged':True, 'wall_seconds':time.perf_counter()-started,
               'binary_sha256':binary_hash, 'baseline_sha256':digest(args.fixture/'baseline.json'),
               'scope':'Fresh file decode, rotation, Vision, native SIFT, measurements and policy. Decision projection excludes raw numerical evidence; decisions, reasons and ordering compared exactly except numerical fields at 1e-12. No app/device/Photos validation.'}
    (args.output/'differences.json').write_text(json.dumps({'decisions':changed,'pairs':pair_changes,'rotation':rotation_changes,'evidence':evidence_changes,'keypoints':keypoint_changes},indent=2))
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    if changed or pair_changes or rotation_changes or summary_changes or evidence_changes or keypoint_changes:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
