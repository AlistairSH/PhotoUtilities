"""Read-only Czkawka CLI benchmark against saved Vision+SIFT comparisons."""
import argparse
import itertools
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

# Cache disabled, no destructive action, exact dataset membership checked beforehand.
CONFIGS = [
    ('default', 'Gradient', 16, 'Nearest', 5),
    ('gradient16-10', 'Gradient', 16, 'Nearest', 10),
    ('gradient16-20', 'Gradient', 16, 'Nearest', 20),
    ('gradient16-40', 'Gradient', 16, 'Nearest', 40),
    ('gradient8-5', 'Gradient', 8, 'Lanczos3', 5),
    ('gradient8-10', 'Gradient', 8, 'Lanczos3', 10),
    ('mean16-10', 'Mean', 16, 'Lanczos3', 10),
    ('mean16-20', 'Mean', 16, 'Lanczos3', 20),
    ('median16-10', 'Median', 16, 'Lanczos3', 10),
    ('median16-20', 'Median', 16, 'Lanczos3', 20),
    ('gradient32-20', 'Gradient', 32, 'Lanczos3', 20),
    ('gradient32-40', 'Gradient', 32, 'Lanczos3', 40),
]


def memberships(groups, images):
    """Return co-grouped pairs, NOT direct hash distances or guaranteed edges."""
    lookup = {str(Path(row['path']).resolve()): i for i, row in enumerate(images)}
    pairs = set()
    for group in groups:
        indices = []
        for entry in group:
            path = str(Path(entry['path']).resolve())
            if path not in lookup:
                raise ValueError('Unexpected source in Czkawka output: '+path)
            indices.append(lookup[path])
        for a, b in itertools.combinations(sorted(set(indices)), 2):
            pairs.add((a, b))
    return pairs


def command(binary, directory, output, config, threads=2):
    _, algorithm, size, resize, distance = config
    return [str(Path(binary).resolve()), 'image', '-d', str(directory),
            '-x', 'jpg', '-D', 'NONE', '-Q', '-H', '-W', '-N', '-T', str(threads),
            '-m', '1', '-g', algorithm, '-c', str(size), '-z', resize,
            '-s', str(distance), '--geometric-invariance', 'off', '-C', str(output)]


def run(binary, datasets_folder, output):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'similarity_compare'))
    from compare import checksum
    output.mkdir(exist_ok=False)
    datasets = {}
    for file in sorted(datasets_folder.glob('*.json')):
        data = json.loads(file.read_text())
        if isinstance(data, dict) and data.get('analyzer') == 'hash-sift-spike-v1':
            datasets[file.stem] = data
    if not datasets:
        raise ValueError('No baseline datasets')
    protected = {row['path']: row['sha256'] for data in datasets.values() for row in data['images']}
    for path, expected in protected.items():
        if checksum(path) != expected:
            raise ValueError('Changed baseline photo: '+path)
    records = []
    for name, data in datasets.items():
        paths = [Path(row['path']).resolve() for row in data['images']]
        directory = Path(os.path.commonpath([str(p.parent) for p in paths]))
        if set(directory.rglob('*.jpg')) != set(paths):
            raise ValueError('Directory membership differs from explicit baseline')
        print('START', name, len(paths), 'images', flush=True)
        for config in CONFIGS:
            filename = output/(name+'--'+config[0]+'.json')
            args = command(binary, directory, filename, config)
            tick = time.perf_counter()
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            seconds = time.perf_counter()-tick
            if result.returncode:
                raise RuntimeError(f'Czkawka failed: {result.returncode}: {result.stdout} {result.stderr}')
            groups = json.loads(filename.read_text())
            co_pairs = memberships(groups, data['images'])
            vision_sift = {(p['a'],p['b']) for p in data['pairs'] if p['vision_distance'] < .45 or p['sift_candidate']}
            record = {'dataset': name, 'config': config[0], 'algorithm': config[1],
                      'hash_size': config[2], 'resize': config[3], 'max_difference': config[4],
                      'threads': 2, 'cache': False, 'seconds': seconds, 'groups': len(groups),
                      'co_pairs': sorted(co_pairs), 'overlap_with_combo': len(co_pairs & vision_sift),
                      'new_beyond_combo': len(co_pairs-vision_sift), 'command': args,
                      'stdout': result.stdout, 'stderr': result.stderr}
            records.append(record)
            print(config[0], f'{seconds:.3f}s', len(groups), 'groups', len(co_pairs), 'co-grouped pairs', flush=True)
        # Warm-filesystem repeatability/speed: default uncached 2 threads, then all threads.
        for threads in [2,0]:
            runs = []
            for repeat in range(3):
                filename = output/(name+f'--timing-t{threads}-{repeat}.json')
                tick = time.perf_counter()
                result = subprocess.run(command(binary,directory,filename,CONFIGS[0],threads),capture_output=True,text=True,timeout=120)
                seconds = time.perf_counter()-tick
                if result.returncode:
                    raise RuntimeError(result.stderr)
                groups = json.loads(filename.read_text())
                runs.append({'seconds':seconds,'co_pairs':sorted(memberships(groups,data['images']))})
            records.append({'dataset':name,'config':f'timing-default-t{threads}','runs':runs,
                            'median_seconds':statistics.median(r['seconds']for r in runs)})
    for path, expected in protected.items():
        if checksum(path) != expected:
            raise ValueError('Photo checksum changed: '+path)
    result = {'analyzer':'czkawka-compare-v1','binary':str(Path(binary).resolve()),
              'version':subprocess.check_output([str(Path(binary).resolve()),'--version'],text=True).strip(),
              'binary_sha256':checksum(binary),'baseline_folder':str(datasets_folder.resolve()),
              'inputs_unchanged':True,'images':len(protected),'records':records}
    with(output/'benchmark.json').open('x')as f:
        json.dump(result,f,indent=2)
    print('COMPLETE; all input checksums unchanged',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_folder',type=Path)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.binary,args.baseline_folder,args.output.resolve())


if __name__=='__main__':
    main()
