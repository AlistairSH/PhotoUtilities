"""Diagnostic detail measurements using the existing CLI focus implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from photo_utils.focus_measurements import analyze_regions


def main():
    parser = argparse.ArgumentParser()
    for name in ('results', 'vision', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):
        raise ValueError('Private outputs must remain outside Git')
    pilot = json.loads(args.results.read_text())
    native = {(r['id'], r['max_dimension']): r for r in
              json.loads(args.vision.read_text())['rows'] if r.get('status') == 'ok'}
    rows = []
    for image in pilot['images']:
        view = args.results.parent / 'model-views' / (image['id'] + '-1024.png')
        digest = hashlib.sha256(view.read_bytes()).hexdigest()
        if digest != pilot['transforms'][image['id'] + '-1024']['sha256']:
            raise ValueError('Changed model view')
        bgr = cv2.imread(str(view))
        if bgr is None:
            raise ValueError('Undecodable view')
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        detection = native[(image['id'], 1024)]
        if detection['path'] != image['path'] or (detection['width'], detection['height']) != (rgb.shape[1], rgb.shape[0]):
            raise ValueError('Detection geometry mismatch')
        detectors = {}
        for source, target in [('face_quality', 'faces'), ('people', 'people'),
                               ('animals', 'animals'), ('attention', 'attention'),
                               ('objectness', 'objectness')]:
            request = detection['requests'][source]
            if request['status'] != 'ok':
                raise ValueError('Failed detector: ' + source)
            detectors[target] = {'regions': [dict(o) for o in request['observations'] if 'box' in o]}
        rows.append({'id': image['id'], 'group': image['group'], 'kind': image['kind'],
                     'view_sha256': digest, 'max_dimension': 1024,
                     'detail': analyze_regions(rgb, detectors)})
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'results.json').write_text(json.dumps({
        'measurement': 'Existing Gaussian sigma 1 Laplacian variance and Tenengrad on exact 1024 views. Regions remain separate. Texture, grain and contrast affect these measurements; not a calibrated blur probability.',
        'automatic_cull_flags': False, 'rows': rows}, indent=2))
    print(json.dumps({'images': len(rows), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
