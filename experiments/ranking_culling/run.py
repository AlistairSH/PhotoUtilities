"""Rank an existing similarity job, read-only; isolated from the production CLI."""
import argparse
import base64
import copy
import csv
import hashlib
import html
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from photo_utils.database import digest
from photo_utils.similarity_report import render
from quality import SETTINGS, measure
from ranking import rank_group


def implementation_key():
    root = Path(__file__).parent
    return hashlib.sha256(b''.join((root / name).read_bytes()
                         for name in ('faces.swift', 'quality.py'))).hexdigest()


def load_job(database, job_id):
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute("SELECT metadata_json FROM scan_jobs WHERE job_id=? AND job_type='similarity'",
                         (job_id,)).fetchone()
    if row is None:
        raise ValueError('No similarity job with that ID')
    result = json.loads(row[0])
    if result['status'] != 'completed' or not result['groups']:
        raise ValueError('Requires a completed similarity job with groups')
    return result


def decode(paths, helper):
    with tempfile.TemporaryFile() as output:
        result = subprocess.run([str(helper.resolve())], input=json.dumps(list(map(str, paths))).encode(),
                                stdout=output, stderr=subprocess.PIPE, timeout=max(180, len(paths)*10))
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
        output.seek(0)
        count = 0
        completed = False
        for line in output:
            row = json.loads(line)
            if completed:
                raise ValueError('Unexpected native output after completion')
            if row['type'] == 'complete':
                completed = row['images'] == len(paths)
                continue
            if row['type'] != 'image' or row['index'] != count or row['path'] != str(paths[count]):
                raise ValueError('Native image identity mismatch')
            w, h = row['width'], row['height']
            if min(w, h) < 1 or max(w, h) > 1024:
                raise ValueError('Invalid native dimensions')
            rgb = np.frombuffer(base64.b64decode(row['rgba'], validate=True), np.uint8).reshape(h,w,4)[:,:,:3]
            ok, encoded = cv2.imencode('.jpg', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError('Thumbnail encoding failed')
            yield {'path': row['path'], 'analysis': measure(rgb, row['faces']),
                   'face_revision': row['face_revision'],
                   'thumbnail': base64.b64encode(encoded.tobytes()).decode('ascii')}
            count += 1
            print(f'Focus analyzed {count}/{len(paths)}', flush=True)
        if not completed or count != len(paths):
            raise ValueError('Incomplete native analysis')


def make_report(result, analyses, destination):
    ranked = copy.deepcopy(result)
    decisions = []
    annotations = {}
    for number, group in enumerate(ranked['groups'], 1):
        decision = rank_group(group['members'], analyses)
        decisions.append(decision)
        group['members'] = decision['members']
        for position, index in enumerate(group['members'], 1):
            image = ranked['images'][index]
            score = decision['scores'][str(index)]
            selected = ' — provisional first choice' if position == 1 else ''
            annotation = f'<p><strong>Rank {position}{selected}</strong> · {decision["basis"]} focus · relative score {score:.3f}</p>'
            annotation += '<details><summary>Focus measurements</summary><table><tr><th>Scale</th><th>Global Laplacian raw → smoothed</th><th>Global Tenengrad raw → smoothed</th></tr>'
            for dimension, row in analyses[index]['scales'].items():
                raw, smooth = row['global']['raw'], row['global']['smoothed']
                annotation += f'<tr><td>{dimension}</td><td>{raw["laplacian_variance"]:.5g} → {smooth["laplacian_variance"]:.5g}</td><td>{raw["tenengrad"]:.5g} → {smooth["tenengrad"]:.5g}</td></tr>'
                for face_number, face in enumerate(row['faces'], 1):
                    if face['usable']:
                        annotation += f'<tr><td>Face {face_number} ({face["pixels"][0]}×{face["pixels"][1]})</td><td>{face["raw"]["laplacian_variance"]:.5g} → {face["smoothed"]["laplacian_variance"]:.5g}</td><td>{face["raw"]["tenengrad"]:.5g} → {face["smoothed"]["tenengrad"]:.5g}</td></tr>'
            annotation += '</table><p>Uncalibrated measurements; larger values can reflect grain, texture, or contrast.</p></details>'
            annotations[html.escape(os.path.relpath(image['path'], destination.parent))] = annotation
    document = render(ranked, destination, result['created_at'])
    document = document.replace('<h1>Related photos</h1>', '<h1>Experimental focus ranking</h1><p class="note">Local photo trial. Suggested winners need human review. Scores compare members of each group only. Face scores combine 60% mean and 40% minimum; smoothed metrics at 1024 and 512 pixels receive equal weight. Grain reduction is provisional. No culling decisions are made.</p>')
    for label, annotation in annotations.items():
        document = document.replace(f'<figcaption>{label}</figcaption>', f'<figcaption>{label}{annotation}</figcaption>')
    for number, decision in enumerate(decisions, 1):
        marker = f'Set {number} <span'
        document = document.replace(marker, f'Set {number} — {"UNCERTAIN" if decision["uncertain"] else "consistent focus winner"} <span')
        header = f'{len(decision["members"])} photos</span></h3>'
        # Locate this specific set so equal group sizes cannot share explanations.
        start = document.index(f'<section><h3>Set {number} ')
        end = document.index(header, start) + len(header)
        document = document[:end] + '<p class="note">' + html.escape(' '.join(decision['explanation'])) + '</p>' + document[end:]
    document = document.replace('figure{margin:', 'table{font-size:12px}td,th{padding:4px;text-align:left}section .gallery figure:first-child{border:3px solid #155b81}figure{margin:')
    return document, decisions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path.home()/'Library/Application Support/PhotoUtilities/jobs.sqlite3')
    parser.add_argument('--job', required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New directory outside source folders and repository')
    parser.add_argument('--export-analysis', action='store_true', help='Explicit JSON analysis export, also reusable without Vision')
    parser.add_argument('--reuse-analysis', type=Path, help='Reuse a prior explicit export after checksum/version verification')
    args = parser.parse_args()
    result = load_job(args.database, args.job)
    paths = [Path(image['path']) for image in result['images']]
    if any(path.is_symlink() for path in paths):
        raise ValueError('Symlink image inputs are refused')
    hashes = [digest(path) for path in paths]
    if hashes != [image['sha256'] for image in result['images']]:
        raise ValueError('Images changed since grouping; refusing stale groups')
    output = args.output_dir.resolve()
    repository = Path(__file__).resolve().parents[2]
    if output == repository or repository in output.parents or any(output == p.parent or p.parent in output.parents for p in paths):
        raise ValueError('Output must be separate from source directories and repository')
    key = implementation_key()
    if args.reuse_analysis:
        exported = json.loads(args.reuse_analysis.read_text())
        if (exported['implementation_key'] != key or exported['settings'] != SETTINGS
                or exported['paths'] != list(map(str,paths)) or exported['hashes'] != hashes):
            raise ValueError('Reusable analysis identity/version/settings mismatch')
        rows = exported['images']
    else:
        rows = list(decode(paths, args.helper))
    if len(rows) != len(paths) or [row['path'] for row in rows] != list(map(str, paths)):
        raise ValueError('Analysis identity mismatch')
    if hashes != [digest(path) for path in paths]:
        raise ValueError('Sources changed during analysis; no report published')
    analyses = [row['analysis'] for row in rows]
    for image, row in zip(result['images'], rows):
        image['thumbnail'] = row['thumbnail']
    output.mkdir(parents=True, exist_ok=False)
    document, decisions = make_report(result, analyses, output/'ranking.html')
    (output/'ranking.html').write_text(document)
    with (output/'review.csv').open('x', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['group', 'suggested', 'uncertain', 'human_choice', 'agree', 'notes'])
        for n, decision in enumerate(decisions, 1):
            writer.writerow([n, str(paths[decision['suggested']]), decision['uncertain'], '', '', ''])
    if args.export_analysis:
        (output/'analysis.json').write_text(json.dumps({'implementation_key':key, 'settings':SETTINGS,
            'grouping_job':args.job, 'paths':list(map(str,paths)), 'hashes':hashes, 'images':rows,
            'groups':result['groups'], 'rankings':decisions, 'inputs_unchanged':True}, indent=2))
    print(json.dumps({'images':len(paths), 'groups':len(decisions),
        'face_groups':sum(d['basis']=='faces' for d in decisions),
        'uncertain_groups':sum(d['uncertain'] for d in decisions), 'report':str(output/'ranking.html')}))


if __name__ == '__main__':
    main()
