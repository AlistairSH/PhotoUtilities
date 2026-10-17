from pathlib import Path
import shutil,hashlib,json,os
root=Path(__file__).resolve().parent.parent
lab=root/'RestorationLab';old=root/'feasibility'
names=[f'35mm-delayed-processing-{i:02}' for i in range(1,7)]+['35mm-scunet-01','35mm-scunet-sharpen-01','35mm-batch-01']
assert all((old/n).is_dir() for n in names)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
records=[]
def copy(src,dst):
 if dst.exists():raise RuntimeError(f'Collision: {dst}')
 dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 assert sha(src)==sha(dst)
 records.append({'old':str(src.relative_to(root)),'retained':str(dst.relative_to(root)),'sha256':sha(dst)})
for name in names:
 for p in sorted((old/name).iterdir()):
  if p.is_file() and p.suffix in {'.py','.json','.md','.txt','.log'}:
   copy(p,lab/'history'/name/p.name)
 for filename in ['comparison.jpg','pilot-comparison.jpg']:
  p=old/name/filename
  if p.exists():copy(p,lab/'references'/name/p.name)
for i in (1,2,3):
 copy(old/f'35mm-delayed-processing-02/{i}-grayscale.png',lab/f'references/grayscale/{i}.png')
 copy(old/f'35mm-delayed-processing-03/{i}-strong.png',lab/f'references/strong-denoise/{i}.png')
for folder in ['vendor','weights']:
 for p in (old/'35mm-scunet-01'/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts:copy(p,lab/folder/p.relative_to(old/'35mm-scunet-01'/folder))
copy(old/'35mm-scunet-01/requirements-lock.txt',lab/'requirements-lock.txt')
for filename in ['restore_batch.py','verify.py','inputs.json']:
 copy(old/'35mm-batch-01'/filename,lab/filename)
# Retain the original production output manifest before repairing documentation.
copy(root/'Restored/restoration-manifest.json',lab/'history/restoration-manifest-original.json')
# Relocation audit of the reusable environment. Symlinks are inventoried separately.
env=old/'35mm-scunet-01/.venv'
env_records=[]
for p in env.rglob('*'):
 if p.is_symlink():env_records.append({'path':str(p.relative_to(env)),'link':os.readlink(p)})
 elif p.is_file():env_records.append({'path':str(p.relative_to(env)),'sha256':sha(p)})
(lab/'environment-relocation.json').write_text(json.dumps(env_records,indent=2))
shutil.move(str(env),str(lab/'.venv'))
for r in env_records:
 p=lab/'.venv'/r['path']
 assert (os.readlink(p)==r['link']) if 'link' in r else (sha(p)==r['sha256'])
# Repair virtualenv entry points, activation paths and installation metadata.
oldenv=str(env);newenv=str(lab/'.venv');repairs=[]
for p in (lab/'.venv').rglob('*'):
 if p.is_symlink() or not p.is_file():continue
 if p.parent==lab/'.venv/bin' or p.name in {'pyvenv.cfg','direct_url.json'} or p.suffix=='.pth':
  try:s=p.read_text()
  except (UnicodeError,OSError):continue
  if oldenv in s:p.write_text(s.replace(oldenv,newenv));repairs.append(str(p.relative_to(lab)))
(lab/'consolidation-audit.json').write_text(json.dumps({'status':'retained-content-verified; pending active-path checks and old-folder deletion','approved_old_folders':names,'retained_files':records,'environment_files_verified':len(env_records),'environment_path_repairs':repairs},indent=2))
print('Retained and checksum-verified',len(records),'files; relocated environment entries:',len(env_records))
