"""Deterministic synthetic comparison; fixtures/reports only in temporary storage."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    rng = np.random.default_rng(42)
    base = np.full((480, 640, 3), 90, np.uint8)
    for _ in range(45):
        x, y = rng.integers(0, 640), rng.integers(0, 480)
        cv2.circle(base, (int(x), int(y)), int(rng.integers(5, 55)), tuple(map(int, rng.integers(20, 240, 3))), -1)
    cv2.putText(base, 'ARCHIVE 42', (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (240, 180, 30), 4)
    soft = cv2.GaussianBlur(base, (31, 31), 8)
    shallow = soft.copy(); shallow[140:300, 60:450] = base[140:300, 60:450]
    kernel = np.zeros((31, 31)); kernel[15, :] = 1 / 31
    variants = {'sharp': base, 'duplicate': base.copy(), 'soft': soft, 'shallow': shallow,
        'motion': cv2.filter2D(base, -1, kernel),
        'bright': np.clip(base.astype(float) * 1.4 + 25, 0, 255).astype(np.uint8),
        'clipped': np.full_like(base, 255), 'distinct': rng.integers(0, 256, base.shape, dtype=np.uint8)}
    paths = []
    for name, image in variants.items():
        path = folder / (name + '.png'); cv2.imwrite(str(path), image); paths.append(str(path))
    command = [sys.executable, str(Path(__file__).with_name('analyze.py')), '--helper', sys.argv[1], '--source-type', 'digital', *paths]
    result = json.loads(subprocess.run(command, capture_output=True, check=True).stdout)
    for row, name in zip(result['images'], variants): row['path'] = name
    print(json.dumps(result, indent=2))
