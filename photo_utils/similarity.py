"""Local candidate grouping with Vision revision 2 OR conservative SIFT."""
from __future__ import annotations

import base64
import math
import os
import platform
import sqlite3
import shlex
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Sequence, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from . import database
from .similarity_native import SimilarityError, native_rows

VERSION = 'vision2-sift-v1'
EXTENSIONS = {'.jpg', '.jpeg', '.heic', '.heif', '.png', '.tif', '.tiff'}
PARAMETERS: dict[str, Any] = {
    'vision_revision': 2, 'preview_max_dimension': 1024, 'color_space': 'sRGB',
    'crop_and_scale': 'scaleFit', 'sift_features': 500, 'ratio_test': .75,
    'mutual': True, 'ransac_pixels': 3, 'ransac_iterations': 2000,
    'ransac_confidence': .995, 'min_inliers': 12,
    'min_inlier_fraction': .5, 'min_coverage': .1,
    'vision_threshold': .45, 'likely_threshold': .40,
}


def collect_images(targets: Sequence[Path], recursive: bool = False, *, skip_generated: bool = False) -> list[Path]:
    found: set[Path] = set()
    def excluded(path: Path) -> bool:
        return skip_generated and (any(part in ('Blurry','retouches','masters') for part in path.parts)
            or 'retouched' in path.stem or '-retouch' in path.stem)
    for target in targets:
        target = target.expanduser().resolve()
        if target.is_file():
            if target.suffix.lower() not in EXTENSIONS:
                raise SimilarityError(f'Unsupported image extension: {target}')
            if not excluded(target):found.add(target)
        elif target.is_dir():
            for path in target.rglob('*') if recursive else target.iterdir():
                if (path.is_file() and path.suffix.lower() in EXTENSIONS
                        and not any(part.startswith('.') for part in path.relative_to(target).parts)
                        and '.partial' not in path.name and '.before-after.' not in path.name):
                    if not excluded(path):found.add(path.resolve())
        else:
            raise SimilarityError(f'Image or folder does not exist: {target}')
    if not found:
        raise SimilarityError('No supported images found (JPEG, HEIC/HEIF, PNG, single-image TIFF).')
    if len(found) > 500:
        raise SimilarityError('Similarity currently supports up to 500 images per run; select a smaller batch.')
    return sorted(found, key=str)


def coverage(points: NDArray[Any], shape: tuple[int, ...]) -> float:
    if len(points) < 3:
        return 0.0
    return float(cv2.contourArea(cv2.convexHull(points.astype(np.float32))) / (shape[0] * shape[1]))


def sift_pair(a: dict[str, Any], b: dict[str, Any], matcher: Any) -> dict[str, Any]:
    empty: dict[str, Any] = {'mutual_matches': 0, 'inliers': 0, 'inlier_fraction': 0.0,
                            'coverage_a': 0.0, 'coverage_b': 0.0, 'sift_candidate': False}
    if a['descriptors'] is None or b['descriptors'] is None or min(len(a['points']), len(b['points'])) < 2:
        return empty
    def good(matches: Any) -> set[tuple[int, int]]:
        return {(m[0].queryIdx, m[0].trainIdx) for m in matches
                if len(m) == 2 and m[0].distance < .75 * m[1].distance}
    forward = good(matcher.knnMatch(a['descriptors'], b['descriptors'], k=2))
    reverse = {(j, i) for i, j in good(matcher.knnMatch(b['descriptors'], a['descriptors'], k=2))}
    mutual = sorted(forward & reverse)
    empty['mutual_matches'] = len(mutual)
    if len(mutual) < 8:
        return empty
    source = np.asarray([a['points'][i] for i, _ in mutual], dtype=np.float32)
    target = np.asarray([b['points'][j] for _, j in mutual], dtype=np.float32)
    cv2.setRNGSeed(0)
    # OpenCV's stubs omit None, which is returned for failed geometry.
    matrix, mask = cast(tuple[Optional[NDArray[Any]], Optional[NDArray[Any]]],
                        cv2.findHomography(source, target, cv2.RANSAC, 3.0, maxIters=2000, confidence=.995))
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        return empty
    selected = mask.ravel().astype(bool)
    count = int(selected.sum())
    ca, cb = coverage(source[selected], a['shape']), coverage(target[selected], b['shape'])
    fraction = count / len(mutual)
    return {'mutual_matches': len(mutual), 'inliers': count, 'inlier_fraction': fraction,
            'coverage_a': ca, 'coverage_b': cb,
            'sift_candidate': bool(count >= 12 and fraction >= .5 and min(ca, cb) >= .1)}


def classify(distance: float, sift: bool, threshold: float = .45) -> str:
    if not math.isfinite(distance) or distance < 0:
        raise SimilarityError('Invalid Vision distance.')
    vision = distance < threshold
    if not vision and not sift:
        return 'unmatched'
    return 'likely' if vision and (distance < .40 or sift) else 'potential'


def components(count: int, pairs: Sequence[dict[str, Any]], *, likely_only: bool = False) -> list[list[int]]:
    adjacency: list[set[int]] = [set() for _ in range(count)]
    for pair in pairs:
        if pair['level'] == 'unmatched' or (likely_only and pair['level'] != 'likely'):
            continue
        a, b = int(pair['a']), int(pair['b'])
        adjacency[a].add(b)
        adjacency[b].add(a)
    unseen = set(range(count))
    groups: list[list[int]] = []
    while unseen:
        stack = [min(unseen)]
        members: set[int] = set()
        while stack:
            i = stack.pop()
            if i in members:
                continue
            members.add(i)
            stack.extend(adjacency[i] - members)
        unseen -= members
        groups.append(sorted(members))
    return sorted(groups, key=lambda group: (-len(group), group))


def analyze(paths: Sequence[Path], hashes: Sequence[str], threshold: float = .45, *, focus: bool = False) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, int]] = set()
    completed = False
    detector: Any = cast(Any, cv2).SIFT_create(nfeatures=500)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    focus_rows: list[dict[str, Any]] = []
    stream = native_rows(paths, focus=True) if focus else native_rows(paths)
    for row in stream:
        if completed:
            raise SimilarityError('Unexpected native output after completion.')
        if row['type'] == 'image':
            index = len(images)
            if index >= len(paths) or row['index'] != index or row['path'] != str(paths[index]) or row['revision'] != 2:
                raise SimilarityError('Native image identity or Vision revision mismatch.')
            w, h = int(row['width']), int(row['height'])
            if min(w, h) < 1 or max(w, h) > 1024:
                raise SimilarityError('Invalid native preview dimensions.')
            rgba = np.frombuffer(base64.b64decode(row['rgba'], validate=True), np.uint8).reshape(h, w, 4)
            if focus:
                from .focus import measure
                focus_rows.append(measure(rgba[:, :, :3], row['detectors'], row['path'], 1024))
            gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
            keypoints, descriptors = detector.detectAndCompute(gray, None)
            features.append({'points': np.asarray([k.pt for k in cast(Sequence[Any], keypoints)], dtype=np.float32),
                             'descriptors': descriptors, 'shape': gray.shape})
            bgr = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR)
            scale = min(1., 512 / max(w, h))
            small = cv2.resize(bgr, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise SimilarityError('Could not encode local report thumbnail.')
            images.append({'path': str(paths[index]), 'sha256': hashes[index], 'width': w,
                           'height': h, 'sift_features': len(keypoints),
                           'thumbnail': base64.b64encode(encoded.tobytes()).decode('ascii'),
                           **({'detectors':row['detectors']} if focus else {})})
            print(f'Analyzed {index + 1}/{len(paths)} images', flush=True)
        elif row['type'] == 'focus':
            if not focus or not images or row['index'] != len(images)-1 or row['path'] != images[-1]['path'] or row['max_dimension'] != 2048:
                raise SimilarityError('Invalid focus row identity.')
            if len(focus_rows) != 2*len(images)-1:
                raise SimilarityError('Missing or duplicate focus resolution.')
            w,h=int(row['width']),int(row['height'])
            if min(w,h)<1 or max(w,h)>2048:raise SimilarityError('Invalid focus image dimensions.')
            rgba=np.frombuffer(base64.b64decode(row['rgba'],validate=True),np.uint8).reshape(h,w,4)
            from .focus import measure
            focus_rows.append(measure(rgba[:,:,:3],row['detectors'],row['path'],2048))
        elif row['type'] == 'pair':
            a, b = int(row['a']), int(row['b'])
            if len(images) != len(paths) or not 0 <= a < b < len(paths) or (a, b) in seen_pairs:
                raise SimilarityError('Invalid or duplicate native comparison.')
            seen_pairs.add((a, b))
            distance = float(row['vision_distance'])
            sift = sift_pair(features[a], features[b], matcher)
            pairs.append({'a': a, 'b': b, 'vision_distance': distance, **sift,
                          'level': classify(distance, sift['sift_candidate'], threshold)})
            if len(pairs) % 500 == 0:
                print(f'Compared {len(pairs)}/{len(paths) * (len(paths) - 1) // 2} pairs', flush=True)
        elif row['type'] == 'complete':
            completed = row['images'] == len(paths)
        else:
            raise SimilarityError('Unknown native response type.')
    if not completed or len(images) != len(paths) or len(pairs) != len(paths) * (len(paths) - 1) // 2:
        raise SimilarityError('Incomplete local Vision analysis; no report was published.')
    strong = components(len(paths), pairs, likely_only=True)
    groups: list[dict[str, Any]] = []
    unmatched: list[int] = []
    for members in components(len(paths), pairs):
        if len(members) == 1:
            unmatched.extend(members)
        else:
            groups.append({'members': members, 'level': 'likely' if members in strong else 'potential'})
    result = {'analyzer': VERSION, 'parameters': {**PARAMETERS, 'vision_threshold': threshold},
            'backends': {'opencv': cv2.__version__, 'numpy': np.__version__, 'os': platform.platform()},
            'images': images, 'pairs': pairs, 'groups': groups, 'unmatched': sorted(unmatched)}
    if focus:
        if len(focus_rows)!=2*len(paths):raise SimilarityError('Incomplete focus measurements.')
        from .focus import decisions, relative_focus, PARAMETERS as FOCUS_PARAMETERS, VERSION as FOCUS_VERSION
        by_path={d['path']:d for d in decisions(focus_rows)}
        for image in images:image['focus_review']=by_path[image['path']]
        result['focus_parameters']=FOCUS_PARAMETERS;result['focus_version']=FOCUS_VERSION
        result['focus_rows']=focus_rows
        relative_focus(result,focus_rows)
    return result


def report_location(targets: Sequence[Path], paths: Sequence[Path], report: Optional[Path]) -> Path:
    if report is not None:
        destination = report.expanduser().resolve()
        if destination.suffix.lower() != '.html':
            raise SimilarityError('Report path must end in .html.')
        if destination.exists():
            raise SimilarityError(f'Refusing to overwrite existing report: {destination}')
        if not destination.parent.is_dir():
            raise SimilarityError('Report parent folder must already exist.')
        return destination
    if len(targets) == 1 and targets[0].expanduser().is_dir():
        return targets[0].expanduser().resolve() / 'similarity.html'
    parents = {path.parent for path in paths}
    if len(parents) != 1:
        raise SimilarityError('Images span multiple folders; supply --report /existing/folder/similarity.html.')
    return next(iter(parents)) / 'similarity.html'


def publish_report(destination: Path, contents: str, *, versioned: bool) -> Path:
    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         prefix='.similarity-', suffix='.partial', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        counter = 1
        while True:
            candidate = destination if counter == 1 else destination.with_name(f'{destination.stem}-v{counter:02d}.html')
            try:
                os.link(temporary, candidate)
                return candidate
            except FileExistsError:
                if not versioned:
                    raise SimilarityError(f'Refusing to overwrite existing report: {candidate}')
                counter += 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def persist_result(db: sqlite3.Connection, job: str, result: dict[str, Any]) -> None:
    # Analysis recipes anchor groups to source asset identities. Existing parent
    # links expose the same analysis from derivative history without rematching.
    for index, image in enumerate(result['images']):
        row = db.execute('SELECT asset_id,sha256 FROM assets WHERE path=?', (image['path'],)).fetchone()
        if row is not None:
            if row['sha256'] and row['sha256'] != image['sha256']:
                raise SimilarityError(f'Asset checksum changed; refusing to rewrite history: {image["path"]}')
            asset_id = row['asset_id']
        else:
            asset_id = database.asset(db, image['path'], job=job, sha=image['sha256'])
        image['asset_id'] = asset_id
        membership = next((n for n, group in enumerate(result['groups'], 1) if index in group['members']), None)
        payload = {'algorithm': VERSION, 'parameters': result['parameters'], 'source_sha256': image['sha256'],
                   'group': membership, 'report': result['report'], 'review': 'unreviewed',
                   'disposition': 'candidate' if membership is not None else 'unmatched'}
        if 'focus_review' in image:
            payload['focus_review']=image['focus_review'];payload['focus_comparison']=image.get('focus_comparison')
        db.execute('INSERT INTO recipes VALUES (?,?,?,?,?,?,?,?)',
                   (uuid.uuid5(uuid.NAMESPACE_URL, f'{job}:{asset_id}:similarity').hex, job, asset_id,
                    None, 'similarity', database.now(), VERSION, database.encode(payload)))


def find_similar(targets: Sequence[Path], *, recursive: bool = False, report: Optional[Path] = None,
                 dry_run: bool = False, no_db: bool = False, threshold: float = .45,
                 state_dir: Optional[Path] = None, focus: bool = False) -> Optional[Path]:
    if not math.isfinite(threshold) or not 0 < threshold <= 2:
        raise SimilarityError('Vision threshold must be finite and in (0, 2].')
    paths = collect_images(targets, recursive)
    destination = report_location(targets, paths, report)
    if focus:print('Focus review: Gaussian1 baseline + contrast/scale confirmation; originals analyzed before edits.')
    print(f'Similarity: {len(paths)} images, {len(paths) * (len(paths) - 1) // 2} comparisons; Vision <{threshold:g} OR SIFT')
    print(f'Report: {destination} (a new numbered version if occupied)' if report is None else f'Report: {destination}')
    if dry_run:
        print('Dry run: no decoding, helper build, reports or database writes.')
        return None
    selected = state_dir or cast(Optional[Path], database.STATE.get())
    if selected is None and not no_db:
        bindings: set[Path] = set()
        for path in paths:
            for parent in path.parents:
                binding = parent / '.photo-utils-database'
                if binding.is_file():
                    location = Path(binding.read_text().strip())
                    if location.name != 'jobs.sqlite3' or not location.is_absolute():
                        raise SimilarityError(f'Invalid database binding: {binding}')
                    bindings.add(location.parent)
                    break
        if len(bindings) > 1:
            raise SimilarityError('Inputs are bound to different databases; choose --state-dir explicitly.')
        selected = next(iter(bindings)) if bindings else None
    with database.use_state(selected):
        hashes = [database.digest(p) for p in paths]
        job = uuid.uuid4().hex
        started = database.now()
        payload: dict[str, Any] = {'created_at': started, 'status': 'running', 'algorithm': VERSION,
                                   'source_paths': list(map(str, paths)), 'parameters': {**PARAMETERS, 'vision_threshold': threshold}}
        if not no_db:
            with database.transaction() as db:
                database.save_job(db, job, 'similarity', payload, destination)
        published: Optional[Path] = None
        tick = time.perf_counter()
        try:
            result = analyze(paths, hashes, threshold, focus=True) if focus else analyze(paths, hashes, threshold)
            result['job_id']=job;result['archive_enabled']=not no_db
            result['state_dir']=str(database.state_dir())
            if hashes != [database.digest(p) for p in paths]:
                raise SimilarityError('Source image changed during analysis; no report was published.')
            if focus:
                from .focus_report import render
            else:
                from .similarity_report import render
            published = publish_report(destination, render(result, destination, started), versioned=report is None)
            result['report'] = str(published)
            result['report_sha256'] = database.digest(published)
            result['images'] = [{k: v for k, v in image.items() if k != 'thumbnail'} for image in result['images']]
            payload.update(result)
            payload.update(status='completed', seconds=time.perf_counter() - tick)
            if not no_db:
                with database.transaction() as db:
                    persist_result(db, job, payload)
                    # A versioned filename is recorded in metadata; keep the
                    # planned job output identity immutable in save_job.
                    database.save_job(db, job, 'similarity', payload, destination)
                    db.execute('UPDATE scan_jobs SET output_path=? WHERE job_id=?', (str(published), job))
            print(f'Found {len(result["groups"])} groups; {len(result["unmatched"])} unmatched images.')
            print(f'Saved: {published}')
            if not no_db:
                print(f'Similarity job: {job}')
                if focus:
                    print('Interactive Delete/ZIP review: '+shlex.join(['photo-utils','review',job,'--state-dir',str(database.state_dir())]))
            return published
        except BaseException as exc:
            if not no_db:
                payload.update(status='partial' if published is not None or isinstance(exc, KeyboardInterrupt) else 'failed', error=str(exc))
                with database.transaction() as db:
                    database.save_job(db, job, 'similarity', payload, destination)
            if isinstance(exc, (KeyboardInterrupt, SimilarityError, database.DatabaseError, OSError)):
                raise
            raise SimilarityError(f'Similarity analysis failed: {exc}') from exc
