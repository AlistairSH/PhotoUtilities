"""Build and run the bundled, on-device Vision helper; no external models."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import selectors
import time
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


def native_rows(paths: Sequence[Path], *, focus: bool = False) -> Iterator[dict[str, Any]]:
    helper = native_helper()
    # Stream bounded pixel rows instead of spilling multi-gigabyte RGBA batch
    # exports to disk. Backpressure keeps at most one image row buffered.
    deadline=time.monotonic()+max(180,len(paths)*10)
    with tempfile.TemporaryFile() as errors:
        process=subprocess.Popen([str(helper)]+(["--focus"] if focus else []),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors)
        assert process.stdin is not None and process.stdout is not None
        selector=selectors.DefaultSelector()
        try:
            process.stdin.write(json.dumps([str(p) for p in paths]).encode())
            process.stdin.close()
            selector.register(process.stdout,selectors.EVENT_READ)
            buffer=bytearray()
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0 or not selector.select(remaining):raise SimilarityError('Local Vision analysis timed out.')
                chunk=os.read(process.stdout.fileno(),1024*1024)
                if not chunk:break
                buffer.extend(chunk)
                if len(buffer)>64*1024*1024:raise SimilarityError('Native response exceeded the image-row limit.')
                while True:
                    newline=buffer.find(b'\n')
                    if newline<0:break
                    line=bytes(buffer[:newline]);del buffer[:newline+1]
                    row=json.loads(line)
                    if not isinstance(row,dict):raise SimilarityError('Expected a native JSON object.')
                    yield cast(dict[str,Any],row)
            if buffer:raise SimilarityError('Incomplete native JSON line.')
            result=process.wait(timeout=max(1.,deadline-time.monotonic()))
            if result:
                errors.seek(0)
                raise SimilarityError('Local Vision analysis failed: '+errors.read().decode(errors='replace').strip())
        except (ValueError,UnicodeError,OSError,subprocess.TimeoutExpired) as exc:
            raise SimilarityError(f'Local Vision analysis failed: {exc}') from exc
        finally:
            selector.close()
            if process.poll() is None:
                process.kill();process.wait()
            process.stdout.close()
            if not process.stdin.closed:process.stdin.close()
