"""Disposable file-layer compatibility checks; never use private originals."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import cv2,numpy as np,tifffile
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--decoder',type=Path,required=True);args=parser.parse_args()
root=args.output
if root.resolve().is_relative_to(Path(__file__).resolve().parents[3]):raise ValueError('Synthetic outputs must remain outside repository')
root.mkdir(exist_ok=False,parents=True)
pixels=np.random.default_rng(3).integers(0,256,(80,120,3),dtype=np.uint8)
for ext in ('jpg','png'):assert cv2.imwrite(str(root/('sample.'+ext)),pixels)
tifffile.imwrite(root/'sample.tif',pixels,photometric='rgb')
heic=subprocess.run(['sips','-s','format','heic',str(root/'sample.png'),'--out',str(root/'sample.heic')],capture_output=True,text=True)
rows=[]
for path in sorted(root.glob('sample.*')):
    before=root/(path.name+'-before.png');after=root/(path.name+'-after.png')
    subprocess.run([str(args.decoder),str(path),str(before),'1024'],capture_output=True,check=True)
    args=['exiftool','-overwrite_original','-XMP-dc:Subject=PU-SelectedForEditing','-XMP-xmp:Rating=4']
    if path.suffix in ('.jpg','.tif'):args+=['-IPTC:Keywords=PU-Landscape']
    write=subprocess.run(args+[str(path)],capture_output=True,text=True)
    read=subprocess.run(['exiftool','-j','-G1','-XMP-dc:Subject','-XMP-xmp:Rating','-IPTC:Keywords',str(path)],capture_output=True,text=True,check=True)
    subprocess.run([str(args.decoder),str(path),str(after),'1024'],capture_output=True,check=True)
    equal=np.array_equal(cv2.imread(str(before)),cv2.imread(str(after)))
    rows.append(dict(format=path.suffix,write_returncode=write.returncode,write_output=write.stdout,write_error=write.stderr,metadata=json.loads(read.stdout),decoded_pixels_equal=bool(equal)))
sidecar=root/'sample.xmp'
subprocess.run(['exiftool','-o',str(sidecar),'-XMP-dc:Subject=PU-SelectedForEditing','-XMP-xmp:Rating=4',str(root/'sample.jpg')],capture_output=True,check=True)
result={'scope':'Disposable synthetic files only. App import/search and round trips not tested.','heic_generation_returncode':heic.returncode,'rows':rows,'sidecar_exists':sidecar.is_file()}
(root/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
