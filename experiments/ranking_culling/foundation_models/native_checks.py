"""Explicit synthetic native checks; originals are not needed."""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path
import cv2, numpy as np, tifffile

def main():
    p=argparse.ArgumentParser();p.add_argument('--helper',type=Path,required=True);p.add_argument('--decoder',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='photo-triage-native-') as work:
        root=Path(work);pixels=np.random.default_rng(2).integers(0,256,(80,120,3),dtype=np.uint8);paths=[]
        for ext in ('jpg','png'):
            path=root/('sample.'+ext);assert cv2.imwrite(str(path),pixels);paths.append(path)
        rotated=root/'orientation6.jpg';assert cv2.imwrite(str(rotated),pixels)
        subprocess.run(['exiftool','-overwrite_original','-Orientation#=6',str(rotated)],capture_output=True,check=True);paths.append(rotated)
        single=root/'single.tif';tifffile.imwrite(single,pixels,photometric='rgb');paths.append(single)
        multi=root/'multi.tif'
        with tifffile.TiffWriter(multi) as writer:
            writer.write(pixels,photometric='rgb');writer.write(pixels,photometric='rgb')
        bad=root/'bad.jpg';bad.write_bytes(b'bad');bmp=root/'unsupported.bmp';assert cv2.imwrite(str(bmp),pixels)
        paths.extend([multi,bad,root/'missing.jpg',bmp]);before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        run=subprocess.run([str(a.helper)],input=json.dumps(list(map(str,paths))),capture_output=True,text=True,timeout=120,check=True)
        rows=[json.loads(x) for x in run.stdout.splitlines()]
        assert rows[-1]['type']=='complete' and rows[-1]['images']==8
        assert [r['status'] for r in rows[:-1]]==['ok']*8+['failed']*8
        assert all(v['status']=='ok' for r in rows[:8] for v in r['requests'].values())
        assert (rows[4]['width'],rows[4]['height'])==(80,120)
        view=root/'view.png';decode=subprocess.run([str(a.decoder),str(rotated),str(view),'1024'],capture_output=True,text=True,timeout=30,check=True)
        info=json.loads(decode.stdout);assert (info['width'],info['height'])==(80,120)
        collision=subprocess.run([str(a.decoder),str(rotated),str(view),'1024'],capture_output=True);assert collision.returncode!=0
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==v for p,v in before.items())
        print('Passed synthetic native checks: JPEG/PNG/TIFF; orientation; no upscaling; corrupt/missing/multipage/BMP failures; all seven Vision requests; decoder collision refusal; source checksums.')
if __name__=='__main__':main()
