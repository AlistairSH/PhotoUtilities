from pathlib import Path
import json,hashlib,re,cv2
root=Path(__file__).resolve().parent.parent;r=root/'Restored';lab=root/'RestorationLab'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((r/'restoration-manifest.json').read_text());inventory=[];deleted=[]
for rec in manifest['records']:
 jpg=r/Path(rec['source']).parent.name/Path(rec['source']).name
 a=cv2.imread(str(jpg));assert a is not None,jpg
 inventory.append({'path':str(jpg),'sha256':sha(jpg),'shape':list(a.shape)})
for p in sorted(r.rglob('*.png')):
 jpg=p.with_suffix('.jpg');assert jpg.is_file() and cv2.imread(str(jpg)) is not None
 deleted.append({'path':str(p),'sha256':sha(p),'matching_jpeg':str(jpg)})
(lab/'jpeg-only-cleanup.json').write_text(json.dumps({'authorized':'User requested JPEG-only Restored; remove PNGs with matching JPEGs','deleted_pngs':deleted,'current_jpegs':inventory},indent=2))
for item in deleted:Path(item['path']).unlink()
# Preserve the historical batch provenance; inventory current user-selected JPEGs separately.
(r/'jpeg-inventory.json').write_text(json.dumps({'policy':'JPEG only','files':inventory},indent=2))
p=r/'review.html';s=p.read_text()
s=re.sub(r'href="([^"]+)\.png"',r'href="\1.jpg"',s)
s=re.sub(r' · <a href="([^"]+\.jpg)">PNG</a>','',s)
s=s.replace('PNG masters and quality-95 JPEGs; 16-bit storage adds no recovered source precision.','JPEG copies retained at your request; PNGs removed.')
s=s.replace('Original orientation retained; no cropping or upscaling.','No cropping or upscaling; current JPEG edits and orientation are preserved.')
p.write_text(s)
p=r/'README.md';s=p.read_text();start=s.index('Each roll folder');end=s.index('Open review.html',start)
s=s[:start]+'''Each roll folder contains only the selected JPEG copies. PNGs were removed at
your request. Original source photographs remain unchanged under OldScans01.
Current JPEG edits and rotations are preserved.

'''+s[end:]
s+='\nJPEG-only cleanup: 14 remaining PNGs removed after checking matching JPEGs.\njpeg-inventory.json records the 37 current JPEGs; restoration-manifest.json\nremains the historical original batch record.\n';p.write_text(s)
# Current verification checks the preserved JPEG inventory; original manifest remains provenance.
p=lab/'verify.py';p.write_text('''from pathlib import Path
import json,hashlib,cv2
root=Path(__file__).resolve().parent.parent
out=root/'Restored'
original=json.loads((out/'restoration-manifest.json').read_text())
current=json.loads((out/'jpeg-inventory.json').read_text())['files']
assert len(current)==37
for r in original['records']:
 p=Path(r['source']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['source_sha256']
for r in current:
 p=Path(r['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 a=cv2.imread(str(p));assert a is not None and list(a.shape)==r['shape']
assert not list(out.rglob('*.png'))
print('Verified 37 unchanged sources, 37 current JPEGs, and no PNGs in Restored.')
''')
# Active recipe now defaults to JPEG-only publication; historical runner remains in history.
p=lab/'restore_batch.py';s=p.read_text().replace("save_image(png,np.uint16(np.rint(final*65535)))","# JPEG-only output policy selected by user.").replace('for p in (png,jpg)', 'for p in (jpg,)')
# Resume uses original immutable manifest and still refuses any missing/changed tracked
# outputs; users should run verify.py for the current intentionally edited JPEG collection.
p.write_text(s)
print('Removed PNGs:',len(deleted),'Current JPEGs:',len(inventory))
