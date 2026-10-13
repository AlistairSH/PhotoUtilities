"""Explicit native smoke check: synthetic files only; pass --helper to run."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
import cv2
import numpy as np
import tifffile


def check(helper: Path) -> None:
    with tempfile.TemporaryDirectory(prefix='aesthetics-native-') as work:
        root=Path(work)
        pixels=np.random.default_rng(4).integers(0,256,(80,120,3),dtype=np.uint8)
        paths=[]
        for extension in ('jpg','png'):
            path=root/('sample.'+extension);assert cv2.imwrite(str(path),pixels);paths.append(path)
        rotated=root/'orientation6.jpg';assert cv2.imwrite(str(rotated),pixels)
        subprocess.run(['exiftool','-overwrite_original','-Orientation#=6',str(rotated)],check=True,capture_output=True)
        paths.append(rotated)
        single=root/'single.tif';tifffile.imwrite(single,pixels,photometric='rgb');paths.append(single)
        multi=root/'multi.tif'
        with tifffile.TiffWriter(multi) as writer:
            writer.write(pixels,photometric='rgb');writer.write(pixels,photometric='rgb')
        bad=root/'bad.jpg';bad.write_bytes(b'not an image')
        bmp=root/'unsupported.bmp';assert cv2.imwrite(str(bmp),pixels)
        paths.extend([multi,bad,root/'missing.jpg',bmp])
        before={p:p.read_bytes() for p in paths if p.is_file()}
        result=subprocess.run([str(helper)],input=json.dumps(list(map(str,paths))),text=True,capture_output=True,timeout=60,check=True)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        assert rows[-1]['type']=='complete' and rows[-1]['images']==8
        assert [r['status'] for r in rows[:-1]]==['ok']*4+['failed']*4
        assert rows[2]['orientation']==6 and (rows[2]['preview_width'],rows[2]['preview_height'])==(80,120)
        assert all(p.read_bytes()==b for p,b in before.items())
        print('Native checks passed: JPEG, PNG, single TIFF, EXIF orientation 6; explicit failures for multipage TIFF, corrupt, missing, BMP; unchanged bytes.')
        print(json.dumps([{k:v for k,v in row.items() if k!='preview'} for row in rows],indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--helper',required=True,type=Path);check(p.parse_args().helper)
