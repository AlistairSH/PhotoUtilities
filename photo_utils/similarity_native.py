"""Build and run the bundled, on-device Vision helper; no external models."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterator, Sequence, cast


class SimilarityError(RuntimeError):
    pass


def native_helper() -> Path:
    if platform.system() != 'Darwin':
        raise SimilarityError('Similarity requires macOS 14 or newer and Apple Vision.')
    compiler = shutil.which('xcrun')
    if compiler is None:
        raise SimilarityError('Install Apple Command Line Tools with xcode-select --install to build the Vision helper.')
    source = Path(__file__).parent / 'native' / 'vision.swift'
    key = hashlib.sha256(source.read_bytes() + platform.machine().encode()).hexdigest()[:20]
    cache = Path.home() / 'Library' / 'Caches' / 'PhotoUtilities' / 'vision'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / ('vision-' + key)
    with (cache / 'build.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not target.is_file():
            with tempfile.TemporaryDirectory(prefix='build-', dir=cache) as work:
                temporary = Path(work) / 'vision'
                try:
                    result = subprocess.run([compiler, 'swiftc', '-O', '-module-cache-path',
                                             str(Path(work) / 'modules'), str(source), '-o', str(temporary)],
                                            capture_output=True, text=True, timeout=180)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise SimilarityError(f'Could not build local Vision helper: {exc}') from exc
                if result.returncode:
                    raise SimilarityError('Could not build local Vision helper: ' + result.stderr.strip())
                os.link(temporary, target)
    return target


def native_rows(paths: Sequence[Path]) -> Iterator[dict[str, Any]]:
    helper = native_helper()
    # Spill native JSON lines to temporary storage instead of buffering every
    # 1024px RGBA preview in memory. Temporary pixels are removed on any exit.
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run([str(helper)], input=json.dumps([str(p) for p in paths]).encode(),
                                    stdout=output, stderr=subprocess.PIPE, timeout=max(180, len(paths) * 10))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SimilarityError(f'Local Vision analysis failed: {exc}') from exc
        if result.returncode:
            raise SimilarityError('Local Vision analysis failed: ' + result.stderr.decode(errors='replace').strip())
        output.seek(0)
        try:
            for line in output:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('Expected a JSON object')
                yield cast(dict[str, Any], row)
        except (ValueError, UnicodeError) as exc:
            raise SimilarityError(f'Invalid response from local Vision helper: {exc}') from exc
