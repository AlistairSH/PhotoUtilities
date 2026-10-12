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
from datetime import datetime
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
    # Reserve the destination without replacement before unlinking the source.
    # An interruption may leave two valid links; restore handles that state.
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
        archive_id=uuid.uuid4().hex;folder=dated_folder(root)
        staging=folder/'.pending';staging.mkdir()
        plan: list[dict[str, Any]]=[]
        for n,(path,sha) in enumerate(sorted(paths.items(),key=lambda item:str(item[0])),1):
            info=path.stat()
            if info.st_dev!=folder.stat().st_dev:raise SimilarityError('Archive staging and sources must share a filesystem; choose --archive-root there.')
            plan.append({'source':str(path),'staged':str(staging/f'{n:04d}-{path.name}'),
                'member':f'photos/{n:04d}-{path.name}','sha256':sha,
                'mtime_ns':info.st_mtime_ns,'mode':stat.S_IMODE(info.st_mode)})
        archive=folder/'deleted-photos.zip'
        record: dict[str, Any]={'created_at':database.now(),'status':'running','algorithm':'review-archive-v2',
            'review_job':job_id,'selected_indices':selected,'files':plan,'archive':str(archive),
            'parameters':{'companions':sorted(COMPANIONS),'recovery':'verified ZIP only; restore by member checksum'}}
        with database.transaction() as db:database.save_job(db,archive_id,'review-archive',record,folder,parent=job_id)
        moved: list[dict[str, Any]]=[]
        committed=False
        try:
            with tempfile.NamedTemporaryFile(dir=folder,suffix='.partial',delete=False) as temp:temporary=Path(temp.name)
            with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
                for item in plan:
                    checked(Path(item['source']),item['sha256']);z.write(item['source'],item['member'])
                z.writestr('archive-index.json',json.dumps({'review_job':job_id,'files':plan},indent=2))
            verify_zip(temporary,plan)
            with temporary.open('rb') as stream:os.fsync(stream.fileno())
            os.link(temporary,archive);temporary.unlink()
            # Reversible staging permits rollback until the archive location and
            # asset states have committed. Loose copies are temporary, not storage.
            for item in plan:
                source=Path(item['source']);checked(source,item['sha256'])
                move_no_replace(source,Path(item['staged']));moved.append(item)
            record.update(status='completed',zip_sha256=database.digest(archive))
            with database.transaction() as db:
                mark_zip_assets(db,archive_id,record)
                database.save_job(db,archive_id,'review-archive',record,folder,parent=job_id)
            committed=True
            cleanup_errors=remove_verified_loose_copies(record)
            if cleanup_errors:
                record.update(status='partial',cleanup_errors=cleanup_errors)
                with database.transaction() as db:database.save_job(db,archive_id,'review-archive',record,folder,parent=job_id)
            return {'archive_job':archive_id,'archive':str(archive),'files':len(plan),'selected_indices':selected,
                'cleanup_warning':'; '.join(cleanup_errors),
                'restore_command':shlex.join(['photo-utils','restore-archive',archive_id,'--state-dir',str(database.state_dir())])}
        except BaseException as exc:
            rollback_errors: list[str]=[]
            if not committed:
                for item in reversed(moved):
                    try:move_no_replace(Path(item['staged']),Path(item['source']))
                    except OSError as error:rollback_errors.append(str(error))
            record.update(status='partial' if committed or rollback_errors else 'failed',error=str(exc),rollback_errors=rollback_errors)
            with database.transaction() as db:database.save_job(db,archive_id,'review-archive',record,folder,parent=job_id)
            raise


def dated_folder(root: Path, created: Optional[str] = None) -> Path:
    """Reserve a human-readable date name without overwriting earlier batches."""
    day=(created or database.now())[:10].replace('-','')
    counter=1
    while True:
        suffix='' if counter==1 else f'-{counter:02d}'
        folder=root/f'{day}-archive{suffix}'
        try:folder.mkdir();return folder
        except FileExistsError:counter+=1


def zip_digest(archive: Path, member: str) -> str:
    with zipfile.ZipFile(archive) as z, z.open(member) as stream:
        h=hashlib.sha256()
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def verify_zip(archive: Path, plan: Sequence[dict[str, Any]]) -> None:
    try:
        checked(archive)
        for item in plan:
            if zip_digest(archive,item['member'])!=item['sha256']:raise SimilarityError('ZIP verification failed; sources retained.')
    except (OSError,KeyError,zipfile.BadZipFile) as exc:raise SimilarityError(f'ZIP verification failed: {exc}') from exc


def mark_zip_assets(db: Any, job_id: str, record: dict[str, Any]) -> None:
    # Keep historical source paths and IDs. Archived bytes are located by ZIP
    # metadata, not by pretending each member is a separate filesystem file.
    for item in record['files']:
        legacy=item.get('archived',item['source'])
        row=db.execute('SELECT asset_id,metadata_json FROM assets WHERE path=?',(legacy,)).fetchone()
        if row is None:row=db.execute('SELECT asset_id,metadata_json FROM assets WHERE path=?',(item['source'],)).fetchone()
        metadata: dict[str, Any]=json.loads(row['metadata_json']) if row else {}
        metadata.update(archive_job=job_id,original_path=item['source'],archive=record['archive'],archive_member=item['member'])
        asset_id=row['asset_id'] if row else database.asset(db,item['source'],job=job_id,sha=item['sha256'],metadata=metadata)
        db.execute("UPDATE assets SET path=?,filename=?,status='archived',metadata_json=? WHERE asset_id=?",
                   (item['source'],Path(item['source']).name,database.encode(metadata),asset_id))


def remove_verified_loose_copies(record: dict[str, Any]) -> list[str]:
    errors: list[str]=[];directories: set[Path]=set()
    for item in record['files']:
        for key in ('staged','archived'):
            if not item.get(key):continue
            path=Path(item[key]);directories.add(path.parent)
            if not path.exists():continue
            try:
                checked(path,item['sha256'])
                if zip_digest(Path(record['archive']),item['member'])!=item['sha256']:raise SimilarityError('ZIP member changed; loose original retained.')
                path.unlink()  # Sole retained archival copy is now the verified ZIP.
            except (OSError,KeyError,SimilarityError,zipfile.BadZipFile) as exc:errors.append(str(exc))
    for directory in directories:
        try:
            finder=directory/'.DS_Store'
            if finder.is_file() and not finder.is_symlink():finder.unlink()
            directory.rmdir()
        except OSError:pass  # Never remove unexpected files or nonempty folders.
    return errors


def read_archived_asset(metadata: dict[str, Any], sha: str) -> bytes:
    with zipfile.ZipFile(metadata['archive']) as z:data=z.read(metadata['archive_member'])
    if hashlib.sha256(data).hexdigest()!=sha:raise SimilarityError('Archived image checksum changed.')
    return data


def extract_member(record: dict[str, Any], item: dict[str, Any], destination: Path) -> None:
    """Verify into a sibling temporary file, then publish without replacement."""
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary: Optional[Path]=None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent,suffix='.partial',delete=False) as out:
            temporary=Path(out.name);h=hashlib.sha256()
            with zipfile.ZipFile(record['archive']) as z, z.open(item['member']) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):out.write(block);h.update(block)
                info=z.getinfo(item['member'])
            out.flush();os.fsync(out.fileno())
        if h.hexdigest()!=item['sha256']:raise SimilarityError('Restore member checksum failed.')
        mode=item.get('mode',stat.S_IMODE(info.external_attr>>16))
        os.chmod(temporary,mode or 0o600)
        stamp=item.get('mtime_ns',int(datetime(*info.date_time).timestamp()*1_000_000_000))
        os.utime(temporary,ns=(stamp,stamp))
        move_no_replace(temporary,destination)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()


def restore_archive(job_id: str) -> None:
    details=database.job_details(job_id);record=details['job']['metadata']
    if details['job']['job_type']!='review-archive':raise SimilarityError('Choose a review-archive job.')
    plan=record['files'];folder=Path(details['job']['output_path']);root=folder.parent
    with (root/'.archive.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        verify_zip(Path(record['archive']),plan)
        todo: list[dict[str, Any]]=[]
        for item in plan:
            source=Path(item['source'])
            if source.exists():
                checked(source,item['sha256']);continue
            todo.append(item)
        restored: list[dict[str, Any]]=[]
        try:
            for item in todo:extract_member(record,item,Path(item['source']));restored.append(item)
            with database.transaction() as db:
                for item in plan:
                    db.execute("UPDATE assets SET path=?,status='completed' WHERE path IN (?,?)",
                               (item['source'],item['source'],item.get('archived',item['source'])))
                record['restored_at']=database.now();record['status']='completed'
                database.save_job(db,job_id,'review-archive',record,folder)
        except BaseException:
            for item in reversed(restored):
                source=Path(item['source']);checked(source,item['sha256']);source.unlink()
            raise
    print(f'Restored {len(todo)} files from ZIP; archive retained: {record["archive"]}')


def compact_archive(job_id: str) -> dict[str, Any]:
    """Convert an existing verified archive to dated ZIP-only storage."""
    details=database.job_details(job_id);record=details['job']['metadata']
    if details['job']['job_type']!='review-archive' or record['status'] not in ('completed','partial'):raise SimilarityError('Choose a published review archive.')
    old_folder=Path(details['job']['output_path']);root=old_folder.parent;old_archive=Path(record['archive'])
    with (root/'.archive.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        checked(old_archive,record.get('zip_sha256'))
        verify_zip(old_archive,record['files'])
        # Check all duplicate originals before making any migration or removal.
        for item in record['files']:
            for key in ('archived','staged'):
                if item.get(key) and Path(item[key]).exists():checked(Path(item[key]),item['sha256'])
        folder=old_folder if old_folder.name.startswith(record['created_at'][:10].replace('-','')+'-archive') else dated_folder(root,record['created_at'])
        archive=folder/'deleted-photos.zip'
        if archive!=old_archive:os.link(old_archive,archive)
        record['previous_archive']=str(old_archive);record['archive']=str(archive)
        record['parameters']['recovery']='verified ZIP only; restore by member checksum'
        with database.transaction() as db:
            if not record.get('restored_at'):mark_zip_assets(db,job_id,record)
            database.save_job(db,job_id,'review-archive',record,old_folder)
            db.execute('UPDATE scan_jobs SET output_path=? WHERE job_id=?',(str(folder),job_id))
        errors=remove_verified_loose_copies(record)
        if archive!=old_archive:
            checked(archive,record.get('zip_sha256'));old_archive.unlink()
            finder=old_folder/'.DS_Store'
            if finder.is_file() and not finder.is_symlink():finder.unlink()
            try:old_folder.rmdir()
            except OSError:pass
        record.update(status='partial' if errors else 'completed',cleanup_errors=errors,storage='zip-only')
        with database.transaction() as db:database.save_job(db,job_id,'review-archive',record,folder)
    return {'archive_job':job_id,'archive':str(archive),'cleanup_errors':errors}
