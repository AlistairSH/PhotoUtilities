"""Read-only pHash/dHash/SIFT benchmark against an explicit saved Vision export."""
import argparse
import base64
import hashlib
import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

VERSION = 'hash-sift-spike-v1'


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def hashes(gray):
    # Independent OpenCV implementations; not bit-compatible with Pillow ImageHash.
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8]
    phash = (low > np.median(low)).flatten()
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    dhash = (small[:, 1:] > small[:, :-1]).flatten()
    return phash, dhash


def coverage(points, shape):
    if len(points) < 3:
        return 0.0
    return float(cv2.contourArea(cv2.convexHull(points.astype(np.float32))) / (shape[0] * shape[1]))


def sift_pair(a, b, matcher):
    # Symmetric ratio test: a point must independently prefer its partner both ways.
    empty = {'mutual_matches': 0, 'inliers': 0, 'inlier_fraction': 0.0,
             'coverage_a': 0.0, 'coverage_b': 0.0, 'sift_strength': 0.0,
             'sift_candidate': False, 'status': 'insufficient-matches'}
    if a['descriptors'] is None or b['descriptors'] is None or min(len(a['points']), len(b['points'])) < 2:
        return {**empty, 'status': 'insufficient-features'}
    forward = matcher.knnMatch(a['descriptors'], b['descriptors'], k=2)
    reverse = matcher.knnMatch(b['descriptors'], a['descriptors'], k=2)
    def good(matches):
        return {(m[0].queryIdx, m[0].trainIdx) for m in matches
                if len(m) == 2 and m[0].distance < 0.75 * m[1].distance}
    mutual = sorted(good(forward) & {(j, i) for i, j in good(reverse)})
    empty['mutual_matches'] = len(mutual)
    if len(mutual) < 8:
        return empty
    source = np.float32([a['points'][i] for i, _ in mutual])
    target = np.float32([b['points'][j] for _, j in mutual])
    cv2.setRNGSeed(0)
    matrix, mask = cv2.findHomography(source, target, cv2.RANSAC, 3.0,
                                     maxIters=2000, confidence=0.995)
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        return {**empty, 'status': 'geometry-failed'}
    selected = mask.ravel().astype(bool)
    count = int(selected.sum())
    ca = coverage(source[selected], a['shape'])
    cb = coverage(target[selected], b['shape'])
    fraction = count / len(mutual)
    strength = count * fraction * min(ca, cb)
    return {'mutual_matches': len(mutual), 'inliers': count,
            'inlier_fraction': fraction, 'coverage_a': ca, 'coverage_b': cb,
            'sift_strength': strength,
            'sift_candidate': bool(count >= 12 and fraction >= 0.5 and min(ca, cb) >= 0.1),
            'status': 'geometry-estimated'}


def compare(report, helper, native_batch_size=8):
    cv2.setNumThreads(2)
    data = json.loads(Path(report).read_text())
    paths = [Path(row['path']) for row in data['images']]
    integrity_started = time.perf_counter()
    before = [checksum(p) for p in paths]
    initial_integrity_seconds = time.perf_counter() - integrity_started
    if before != [row['sha256'] for row in data['images']]:
        raise ValueError('Inputs differ from saved Vision baseline')
    if native_batch_size < 1:
        raise ValueError("Native batch size must be positive")
    refreshed_distances = {}
    features = []
    image_rows = []
    native_seconds = 0.0
    extraction = 0.0
    hash_seconds = 0.0
    started = time.perf_counter()
    # Small native batches cap bridge payload/memory; original Vision distances reused.
    for offset in range(0, len(paths), native_batch_size):
        result = subprocess.run([str(Path(helper).resolve()), *map(str, paths[offset:offset+native_batch_size])],
                                capture_output=True, check=True, timeout=120)
        decoded = json.loads(result.stdout)
        native_seconds += decoded['seconds']
        for pair in decoded['pairs']:
            refreshed_distances[(offset+pair['a'], offset+pair['b'])] = pair['vision_distance']
        for row, expected in zip(decoded['images'], data['images'][offset:offset+native_batch_size]):
            if row['path'] != expected['path'] or (row['width'], row['height'], row['revision']) != (expected['width'], expected['height'], expected['revision']):
                raise ValueError('Preview identity/dimensions/revision differ from baseline')
            rgba = np.frombuffer(base64.b64decode(row['rgba']), np.uint8).reshape(row['height'], row['width'], 4)
            gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
            tick = time.perf_counter()
            phash, dhash = hashes(gray)
            hash_seconds += time.perf_counter() - tick
            tick = time.perf_counter()
            detector = cv2.SIFT_create(nfeatures=500)
            keypoints, descriptors = detector.detectAndCompute(gray, None)
            extraction += time.perf_counter() - tick
            features.append({'points': np.float32([k.pt for k in keypoints]),
                             'descriptors': descriptors, 'shape': gray.shape,
                             'phash': phash, 'dhash': dhash})
            image_rows.append({'path': row['path'], 'sha256': expected['sha256'],
                               'sift_features': len(keypoints), 'width': row['width'], 'height': row['height']})
        print('Decoded', min(offset+native_batch_size, len(paths)), '/', len(paths), flush=True)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    rows = []
    tick = time.perf_counter()
    for index, pair in enumerate(data['pairs']):
        a, b = features[pair['a']], features[pair['b']]
        rows.append({**pair, 'vision_distance': refreshed_distances.get((pair['a'],pair['b']),pair['vision_distance']), 'phash_hamming': int(np.count_nonzero(a['phash'] != b['phash'])),
                     'dhash_hamming': int(np.count_nonzero(a['dhash'] != b['dhash'])),
                     **sift_pair(a, b, matcher)})
        if (index+1) % 500 == 0:
            print('Compared', index+1, '/', len(data['pairs']), flush=True)
    matching = time.perf_counter() - tick
    integrity_started = time.perf_counter()
    after = [checksum(p) for p in paths]
    final_integrity_seconds = time.perf_counter() - integrity_started
    if before != after:
        raise ValueError('Input checksum changed during benchmark')
    return {'analyzer': VERSION, 'opencv': cv2.__version__, 'images': image_rows,
            'pairs': rows, 'inputs_unchanged': True, 'baseline': str(Path(report).resolve()),
            'parameters': {'phash_bits': 64, 'dhash_bits': 64, 'sift_max_features': 500,
                           'ratio_test': 0.75, 'mutual': True, 'ransac_pixels': 3,
                           'min_inliers': 12, 'min_inlier_fraction': 0.5, 'min_coverage': 0.1,
                           'vision_revision': 2, 'vision_thresholds': [0.4, 0.45],
                           'native_batch_size': native_batch_size,
                           'all_vision_distances_refreshed': len(refreshed_distances) == len(data['pairs'])},
            'seconds': {'native_decode_and_featureprints': native_seconds,
                        'hash_extraction': hash_seconds, 'sift_extraction': extraction,
                        'pair_comparison': matching, 'wall_excluding_initial_hashing': time.perf_counter()-started,
                        'initial_integrity_hashing': initial_integrity_seconds,
                        'final_integrity_hashing': final_integrity_seconds}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    result = compare(args.baseline, args.helper)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2)
    print('Saved', args.output, flush=True)


if __name__ == '__main__':
    main()
