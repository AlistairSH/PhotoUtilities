"""Explicit, repeatable legacy import and verified metadata-only cleanup."""
from contextlib import closing
from pathlib import Path
import json

from . import database as store


def validate(path, value):
    if not isinstance(value,dict) or not isinstance(value.get('algorithm'),str):
        raise store.DatabaseError('Unrecognized metadata format')
    images = []
    if 'cards' in value and 'source_path' in value and 'source_sha256' in value:
        if not isinstance(value['cards'],list):
            raise store.DatabaseError('Invalid cards list')
        images.append((Path(value['source_path']),value['source_sha256']))
        for card in value['cards']:
            name = Path(card['filename'])
            if name.name != str(name) or name.name in {'.','..'}:
                raise store.DatabaseError('Unsafe print filename')
            images.append((path.parent/name,card.get('sha256')))
        kind = 'split'
    elif 'files' in value and 'source_root' in value and isinstance(value.get('source_sha256'),dict):
        if not isinstance(value['files'],list):
            raise store.DatabaseError('Invalid files list')
        images.extend((Path(name),sha) for name,sha in value['source_sha256'].items())
        for item in value['files']:
            relative = Path(item['relative_output'])
            if relative.is_absolute() or '..' in relative.parts:
                raise store.DatabaseError('Unsafe derivative filename')
            images.append((path.parent/relative,item.get('output_sha256')))
        kind = 'retouch'
    elif 'source_path' in value and 'output_path' in value and ('recipe_version' in value or path.name.endswith('.job.json')):
        images = [(Path(value['source_path']),value.get('source_sha256')),(Path(value['output_path']),value.get('output_sha256'))]
        if path.name.endswith('.recipe.json') and store.key(value['output_path']) != store.key(Path(str(path)[:-len('.recipe.json')])):
            raise store.DatabaseError('Ambiguous copied recipe: recorded output differs from adjacent TIFF')
        kind = 'recipe' if 'recipe_version' in value else 'retouch'
    else:
        raise store.DatabaseError('Unrecognized metadata format')
    missing = []
    for image,sha in images:
        if not image.is_file():
            missing.append(str(image))
        elif sha and store.digest(image) != sha:
            raise store.DatabaseError(f'Checksum mismatch: {image}')
    return kind,missing


def candidates(root):
    return sorted({*Path(root).rglob('manifest.json'),*Path(root).rglob('*-prints.manifest.json'),
                   *Path(root).rglob('*.recipe.json'),*Path(root).rglob('*.job.json')})


def migrate(root, dry_run=False):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise store.DatabaseError(f'Migration root is not a directory: {root}')
    summary = dict(imported=0,skipped=0,duplicate=0,failed=0,missing_files=0,details=[])
    ledgers = sorted(root.rglob('.photo-utils-naming.sqlite3'))
    if not dry_run:
        with store.transaction() as db:
            for ledger in ledgers:
                store.import_ledger(db,ledger.parent)
    summary['naming_ledgers'] = len(ledgers)
    parsed = []
    for path in candidates(root):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            kind,missing = validate(path,value)
            parsed.append(({'split':0,'retouch':1,'recipe':2}[kind],path,value,missing))
        except (ValueError,KeyError,TypeError,OSError,store.DatabaseError) as exc:
            if 'Unrecognized metadata format' in str(exc):
                summary['skipped'] += 1
            else:
                summary['failed'] += 1
            summary['details'].append({'path':str(path),'error':str(exc)})
    for _,path,value,missing in sorted(parsed,key=lambda item:(item[0],str(item[1]))):
        try:
            checksum = store.digest(path)
            previous = None
            if store.database_path().is_file():
                with closing(store.raw_connect(store.database_path(),readonly=True)) as db:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_imports'").fetchone():
                        previous = db.execute('SELECT sha256 FROM legacy_imports WHERE path=?',(str(path),)).fetchone()
            if previous:
                if previous[0]!=checksum:
                    raise store.DatabaseError('Previously imported metadata changed; manual review required')
                summary['duplicate'] += 1
                continue
            if not dry_run:
                with store.transaction() as db:
                    # Check again under the write transaction for concurrent imports.
                    prior = db.execute('SELECT sha256 FROM legacy_imports WHERE path=?',(str(path),)).fetchone()
                    if prior:
                        if prior[0]!=checksum:
                            raise store.DatabaseError('Concurrent migration conflict')
                        summary['duplicate'] += 1
                        continue
                    job_id = store.save_record(path,value,db)
                    # Keep the original JSON text as well as relational fields. This
                    # preserves numeric lexemes beyond Python float precision.
                    raw = path.read_text(encoding='utf-8')
                    if store.digest(path)!=checksum:
                        raise store.DatabaseError('Metadata changed during migration')
                    db.execute('UPDATE metadata_records SET payload_json=? WHERE record_key=?',(raw,str(path)))
                    if 'recipe_version' in value:
                        output = db.execute('SELECT asset_id FROM assets WHERE path=?',(store.key(value['output_path']),)).fetchone()
                        db.execute("UPDATE recipes SET payload_json=? WHERE job_id=? AND output_asset_id=? AND stage='retouch'",(raw,job_id,output[0]))
                    else:
                        db.execute('UPDATE scan_jobs SET metadata_json=? WHERE job_id=?',(raw,job_id))
                    db.execute('INSERT INTO legacy_imports VALUES (?,?,?,?,NULL)',(str(path),checksum,str(path),store.now()))
            summary['imported'] += 1
            summary['missing_files'] += len(missing)
            if missing:
                summary['details'].append({'path':str(path),'missing_files':missing})
        except (store.DatabaseError,ValueError,KeyError,TypeError,OSError) as exc:
            summary['failed'] += 1
            summary['details'].append({'path':str(path),'error':str(exc)})
    summary['dry_run'] = dry_run
    if not dry_run:
        checks = store.check_database()
        summary['verified_database'] = checks['database_ok']
        with closing(store.connect()) as db:
            summary['record_counts'] = {table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ['scan_jobs','assets','recipes','metadata_records','legacy_imports']}
    return summary


def cleanup(root, dry_run=False):
    root = Path(root).expanduser().resolve()
    if not store.database_path().is_file():
        return {'removed':0,'eligible':0,'skipped':0,'details':[],'dry_run':dry_run}
    checks = store.check_database()
    if not checks['database_ok']:
        raise store.DatabaseError('Database integrity failed; cleanup is disabled')
    summary = {'removed':0,'eligible':0,'skipped':0,'details':[],'dry_run':dry_run}
    with closing(store.connect()) as db:
        rows = db.execute('''SELECT l.*,m.payload_json FROM legacy_imports l JOIN metadata_records m ON m.record_key=l.record_key
                             WHERE l.cleaned_at IS NULL''').fetchall()
    for row in rows:
        path = Path(row['path'])
        if root not in path.parents or not path.is_file():
            continue
        try:
            if path.is_symlink() or path.suffix!='.json' or path not in candidates(path.parent):
                raise store.DatabaseError('Not an eligible metadata file')
            if store.digest(path)!=row['sha256']:
                raise store.DatabaseError('Legacy metadata changed after migration')
            value = json.loads(path.read_text())
            _,missing = validate(path,value)
            current = json.loads(row['payload_json'])
            if any(current.get(k)!=v for k,v in value.items()) or missing:
                raise store.DatabaseError('Stored metadata or image references do not verify')
            summary['eligible'] += 1
            if not dry_run:
                # Recheck identity and bytes immediately before metadata-only removal.
                with store.transaction() as db:
                    if path.is_symlink() or store.digest(path)!=row['sha256']:
                        raise store.DatabaseError('File changed during cleanup')
                    path.unlink()
                    db.execute('UPDATE legacy_imports SET cleaned_at=? WHERE path=?',(store.now(),str(path)))
                summary['removed'] += 1
        except (OSError,ValueError,KeyError,TypeError,store.DatabaseError) as exc:
            summary['skipped'] += 1
            summary['details'].append({'path':str(path),'error':str(exc)})
    return summary
