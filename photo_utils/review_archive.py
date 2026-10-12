"""Verified, reversible local review archives in the existing job database."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
import stat
import shlex
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional, Sequence
from . import database
from .scanning import default_root
from .similarity_native import SimilarityError

COMPANIONS={'.xmp','.aae','.dng','.cr2','.cr3','.nef','.arw','.raf','.rw2','.orf','.mov','.mp4','.jpg','.jpeg','.heic','.heif'}


def checked(path: Path, sha: Optional[str] = None) -> str:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):raise SimilarityError(f'Not a regular archival source: {path}')
    actual=database.digest(path)
    if sha is not None and actual!=sha:raise SimilarityError(f'File changed since review: {path}')
    return actual


def move_no_replace(source: Path, destination: Path) -> None:
    """Same-filesystem move with atomic no-clobber destination reservation."""
    os.link(source,destination,follow_symlinks=False)
    try:
        source.unlink()
    except BaseException:
        destination.unlink()
        raise


def review_job(job_id: str) -> dict[str, Any]:
    details=database.job_details(job_id);payload=details['job']['metadata']
    if payload.get('status')!='completed' or not payload.get('focus_version'):raise SimilarityError('Choose a completed focus-review job.')
    return payload


def archive_selected(job_id: str, indices: Sequence[int], *, archive_root: Optional[Path] = None) -> dict[str, Any]:
    payload=review_job(job_id);images=payload['images']
    selected=sorted(set(indices))
    if not selected or any(type(i) is not int or i<0 or i>=len(images) for i in selected):raise SimilarityError('Invalid review selection.')
    root=(archive_root or default_root()/'Blurry').expanduser().resolve()
    paths: dict[Path,str]={}
    for i in selected:
        image=images[i];path=Path(image['path']);paths[path]=checked(path,image['sha256'])
        for sibling in path.parent.iterdir():
            if sibling.stem==path.stem and sibling.suffix.lower() in COMPANIONS and sibling!=path:
                paths[sibling]=checked(sibling)
    # Include generated descendants so a deleted original does not remain active
    # as a retouched copy, but never include its parent/master.
    with database.transaction() as db:
        for path in list(paths):
            row=db.execute('SELECT asset_id,asset_type,status FROM assets WHERE path=?',(str(path),)).fetchone()
            if row and row['asset_type']=='master':raise SimilarityError('Scanner masters cannot be archived from a photo review.')
            if row:
                children=db.execute('WITH RECURSIVE family AS (SELECT * FROM assets WHERE parent_asset_id=? UNION ALL SELECT a.* FROM assets a JOIN family f ON a.parent_asset_id=f.asset_id) SELECT * FROM family',(row['asset_id'],)).fetchall()
                for child in children:
                    if child['asset_type']=='master':raise SimilarityError('A review archive cannot include a scanner master.')
                    if child['status']=='archived':continue
                    cp=Path(child['path']);paths[cp]=checked(cp,child['sha256'])
        for path in paths:
            row=db.execute('SELECT asset_type FROM assets WHERE path=?',(str(path),)).fetchone()
            if row and row['asset_type']=='master':raise SimilarityError('Companion list includes a scanner master.')
    if any(root==p.parent or root in p.parents for p in paths):raise SimilarityError('Files already in the archive cannot be selected.')
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.archive.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        archive_id=uuid.uuid4().hex;folder=root/archive_id;folder.mkdir()
        originals=folder/'originals';originals.mkdir()
        plan: list[dict[str, Any]]=[]
        for n,(path,sha) in enumerate(sorted(paths.items(),key=lambda item:str(item[0])),1):
            if path.stat().st_dev!=folder.stat().st_dev:raise SimilarityError('Archive and sources must be on the same filesystem for reversible atomic moves; choose --archive-root on that filesystem.')
            plan.append({'source':str(path),'archived':str(originals/f'{n:04d}-{path.name}'),'member':f'photos/{n:04d}-{path.name}','sha256':sha})
        archive=folder/'deleted-photos.zip'
        record: dict[str, Any]={'created_at':database.now(),'status':'running','algorithm':'review-archive-v1','review_job':job_id,'selected_indices':selected,'files':plan,'archive':str(archive),'parameters':{'companions':sorted(COMPANIONS),'recovery':'verified ZIP plus retained originals; no unlink'}}
        with database.transaction() as db:database.save_job(db,archive_id,'review-archive',record,folder,parent=job_id)
        moved: list[dict[str, Any]]=[]
        try:
            with tempfile.NamedTemporaryFile(dir=folder,suffix='.partial',delete=False) as temp:
                temporary=Path(temp.name)
            with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
                for item in plan:
                    checked(Path(item['source']),item['sha256']);z.write(item['source'],item['member'])
                z.writestr('archive-index.json',json.dumps({'review_job':job_id,'files':plan},indent=2))
            with zipfile.ZipFile(temporary) as z:
                for item in plan:
                    with z.open(item['member']) as stream:
                        h=hashlib.sha256()
                        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
                    if h.hexdigest()!=item['sha256']:raise SimilarityError('ZIP verification failed; sources retained.')
            with temporary.open('rb') as stream:os.fsync(stream.fileno())
            os.link(temporary,archive);temporary.unlink()
            for item in plan:
                source=Path(item['source']);checked(source,item['sha256'])
                move_no_replace(source,Path(item['archived']));moved.append(item)
            with database.transaction() as db:
                for item in plan:
                    row=db.execute('SELECT asset_id,metadata_json FROM assets WHERE path=?',(item['source'],)).fetchone()
                    if row:
                        meta=json.loads(row['metadata_json']);meta.update(archive_job=archive_id,original_path=item['source'],archive=str(archive))
                        db.execute("UPDATE assets SET path=?,status='archived',metadata_json=? WHERE asset_id=?",(item['archived'],database.encode(meta),row['asset_id']))
                    else:
                        asset_id=database.asset(db,item['archived'],job=archive_id,sha=item['sha256'],metadata={'original_path':item['source'],'archive_job':archive_id})
                        db.execute("UPDATE assets SET status='archived' WHERE asset_id=?",(asset_id,))
                record.update(status='completed',zip_sha256=database.digest(archive))
                database.save_job(db,archive_id,'review-archive',record,folder,parent=job_id)
            return {'archive_job':archive_id,'archive':str(archive),'files':len(plan),'selected_indices':selected,'restore_command':shlex.join(['photo-utils','restore-archive',archive_id,'--state-dir',str(database.state_dir())])}
        except BaseException as exc:
            rollback_errors: list[str]=[]
            for item in reversed(moved):
                try:
                    if Path(item['source']).exists():raise SimilarityError('Original path occupied during archive rollback.')
                    move_no_replace(Path(item['archived']),Path(item['source']))
                except OSError as error:rollback_errors.append(str(error))
                except SimilarityError as error:rollback_errors.append(str(error))
            record.update(status='partial' if rollback_errors else 'failed',error=str(exc),rollback_errors=rollback_errors)
            with database.transaction() as db:database.save_job(db,archive_id,'review-archive',record,folder,parent=job_id)
            raise


def restore_archive(job_id: str) -> None:
    details=database.job_details(job_id);record=details['job']['metadata']
    if details['job']['job_type']!='review-archive':raise SimilarityError('Choose a review-archive job.')
    plan=record['files'];folder=Path(details['job']['output_path']);root=folder.parent
    with (root/'.archive.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        todo: list[dict[str, Any]]=[]
        for item in plan:
            source=Path(item['source']);archived=Path(item['archived'])
            if source.exists():
                if archived.exists():
                    # A crash between link/unlink may leave both copies. Never
                    # overwrite either; accept only two verified originals.
                    checked(archived,item['sha256'])
                checked(source,item['sha256']);continue
            checked(archived,item['sha256']);todo.append(item)
        moved: list[dict[str, Any]]=[]
        try:
            for item in todo:
                source=Path(item['source']);source.parent.mkdir(parents=True,exist_ok=True)
                if source.exists():raise SimilarityError(f'Restore path occupied: {source}')
                move_no_replace(Path(item['archived']),source);moved.append(item)
            with database.transaction() as db:
                for item in plan:
                    db.execute("UPDATE assets SET path=?,status='completed' WHERE path=?",(item['source'],item['archived']))
                record['restored_at']=database.now();record['status']='completed'
                database.save_job(db,job_id,'review-archive',record,folder)
        except BaseException:
            for item in reversed(moved):move_no_replace(Path(item['source']),Path(item['archived']))
            raise
    print(f'Restored {len(todo)} files; published ZIP, if present, retained: {record["archive"]}')
