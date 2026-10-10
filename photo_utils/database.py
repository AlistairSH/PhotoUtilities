"""Versioned local metadata repository; images always remain ordinary files."""
from contextlib import contextmanager, closing
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
import fcntl
import hashlib
import json
import os
import sqlite3
import uuid


class DatabaseError(RuntimeError):
    pass


STATE = ContextVar('photo_utils_state', default=None)
CLI_COMMAND = ContextVar('photo_utils_command',default=None)
CLI_CONFIG = ContextVar('photo_utils_cli_config',default=None)
SCHEMA_VERSION = 1


def state_dir():
    return Path(STATE.get() or os.environ.get('PHOTO_UTILITIES_STATE_DIR') or
                Path.home() / 'Library' / 'Application Support' / 'PhotoUtilities').expanduser().resolve()


def database_path():
    return state_dir() / 'jobs.sqlite3'


@contextmanager
def use_state(directory):
    token = STATE.set(directory) if directory is not None else None
    try:
        yield
    finally:
        if token is not None:
            STATE.reset(token)


def scoped_state(function):
    import functools
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        selected = kwargs.get('state_dir')
        if selected is None and STATE.get() is None and args:
            source = Path(args[0]).expanduser().resolve()
            for parent in [source, *source.parents]:
                binding = parent / '.photo-utils-database'
                if binding.is_file():
                    target = Path(binding.read_text().strip())
                    if target.name != 'jobs.sqlite3':
                        raise DatabaseError(f'Invalid database binding: {binding}')
                    selected = target.parent
                    break
        with use_state(selected):
            return function(*args, **kwargs)
    return wrapped


def now():
    return datetime.now().astimezone().isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def raw_connect(path, readonly=False):
    db = sqlite3.connect(path.as_uri() + '?mode=ro' if readonly else str(path),
                         uri=readonly, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def connect(path=None):
    path = Path(path or database_path()).expanduser().resolve()
    if path.is_file():
        current = raw_connect(path)
        version = current.execute('PRAGMA user_version').fetchone()[0]
        if version == SCHEMA_VERSION:
            return current
        current.close()
        if version > SCHEMA_VERSION:
            raise DatabaseError('Database schema is newer than this application.')
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / (path.name + '.schema.lock')).open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existed = path.exists() and path.stat().st_size > 0
        db = raw_connect(path)
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise DatabaseError('Database schema is newer than this application.')
            if version < SCHEMA_VERSION:
                if existed:
                    backup = path.with_name(f'{path.stem}.backup-v{version}-{uuid.uuid4().hex}.sqlite3')
                    with closing(raw_connect(backup)) as target:
                        db.backup(target)
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute('''CREATE TABLE IF NOT EXISTS scan_jobs (
                        job_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
                        status TEXT NOT NULL CHECK(status IN ('running','completed','failed','interrupted')),
                        device TEXT NOT NULL DEFAULT '', output_path TEXT NOT NULL DEFAULT '',
                        partial_path TEXT NOT NULL DEFAULT '', settings_json TEXT NOT NULL DEFAULT '{}',
                        sha256 TEXT, size_bytes INTEGER, error TEXT)''')
                    columns = {row['name'] for row in db.execute('PRAGMA table_info(scan_jobs)')}
                    for name, definition in {
                        'job_type': "TEXT NOT NULL DEFAULT 'scan'",
                        'parent_job_id': 'TEXT REFERENCES scan_jobs(job_id)',
                        'processing_date': "TEXT NOT NULL DEFAULT ''",
                        'processing_status': "TEXT NOT NULL DEFAULT 'running' CHECK(processing_status IN ('pending','running','completed','partial','failed'))",
                        'command': "TEXT NOT NULL DEFAULT ''",
                        'metadata_json': "TEXT NOT NULL DEFAULT '{}'",
                    }.items():
                        if name not in columns:
                            db.execute(f'ALTER TABLE scan_jobs ADD COLUMN {name} {definition}')
                    db.execute("UPDATE scan_jobs SET processing_status=CASE status WHEN 'interrupted' THEN 'partial' ELSE status END, processing_date=replace(substr(started_at,1,10),'-','')")
                    db.execute('''CREATE TABLE IF NOT EXISTS assets (
                        asset_id TEXT PRIMARY KEY, asset_type TEXT NOT NULL CHECK(asset_type IN ('master','print','retouch','external')),
                        parent_asset_id TEXT REFERENCES assets(asset_id), job_id TEXT REFERENCES scan_jobs(job_id),
                        path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL, sha256 TEXT,
                        format TEXT, width INTEGER, height INTEGER, bit_depth INTEGER,
                        created_at TEXT NOT NULL, processing_date TEXT NOT NULL,
                        status TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}')''')
                    db.execute('''CREATE TABLE IF NOT EXISTS recipes (
                        recipe_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES scan_jobs(job_id),
                        source_asset_id TEXT NOT NULL REFERENCES assets(asset_id),
                        output_asset_id TEXT REFERENCES assets(asset_id), stage TEXT NOT NULL,
                        created_at TEXT NOT NULL, algorithm TEXT NOT NULL, payload_json TEXT NOT NULL,
                        UNIQUE(job_id,source_asset_id,output_asset_id,stage))''')
                    db.execute('''CREATE TABLE IF NOT EXISTS metadata_records (
                        record_key TEXT PRIMARY KEY, kind TEXT NOT NULL, job_id TEXT NOT NULL REFERENCES scan_jobs(job_id),
                        payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)''')
                    db.execute('''CREATE TABLE IF NOT EXISTS legacy_imports (
                        path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, record_key TEXT NOT NULL REFERENCES metadata_records(record_key),
                        imported_at TEXT NOT NULL, cleaned_at TEXT)''')
                    db.execute('CREATE TABLE IF NOT EXISTS daily_ids (root TEXT NOT NULL, date TEXT NOT NULL, number INTEGER NOT NULL, PRIMARY KEY(root,date))')
                    db.execute('CREATE TABLE IF NOT EXISTS legacy_sources (source TEXT PRIMARY KEY, root TEXT NOT NULL, date TEXT NOT NULL, number INTEGER NOT NULL)')
                    for table, column in [('scan_jobs','processing_date'),('scan_jobs','job_type'),('scan_jobs','processing_status'),('scan_jobs','parent_job_id'),('assets','processing_date'),('assets','job_id'),('assets','parent_asset_id'),('assets','status'),('recipes','job_id'),('recipes','source_asset_id'),('recipes','output_asset_id'),('recipes','stage'),('recipes','created_at')]:
                        db.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table}({column})')
                    for scan in db.execute("SELECT job_id FROM scan_jobs WHERE job_type='scan'").fetchall():
                        sync_scan(db,scan[0])
                    db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            return db
        except BaseException:
            db.close()
            raise


@contextmanager
def transaction():
    try:
        with closing(connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            with db:
                yield db
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise DatabaseError(f'Local metadata database: {exc}') from exc


def key(path):
    return str(Path(path).expanduser().resolve())


def record_exists(path):
    return read_record(path, missing_ok=True) is not None


def read_record(path, missing_ok=False, legacy=True):
    location = database_path()
    if location.exists():
        with closing(raw_connect(location, readonly=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='metadata_records'").fetchone():
                row = db.execute('SELECT payload_json FROM metadata_records WHERE record_key=?', (key(path),)).fetchone()
                if row:
                    return json.loads(row[0])
    if legacy and Path(path).is_file():
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise DatabaseError(f'Legacy metadata must be a JSON object: {path}')
        return value
    if missing_ok:
        return None
    raise DatabaseError(f'No processing metadata found: {path}')


def processing_date(path, payload=None):
    import re
    payload = payload or {}
    if payload.get('scan_date'):
        return payload['scan_date']
    match = re.search(r'(\d{8})(?:-|T)', Path(path).name)
    if match:
        return match[1]
    return (payload.get('created_at') or now())[:10].replace('-', '')


def asset(db, path, asset_type='external', parent=None, job=None, sha=None, metadata=None, created=None, date=None):
    path = Path(path).expanduser().resolve()
    metadata = metadata or {}
    row = db.execute('SELECT * FROM assets WHERE path=?', (str(path),)).fetchone()
    if row and parent and row['parent_asset_id'] and row['parent_asset_id'] != parent:
        raise DatabaseError(f'Ambiguous parent for {path}')
    if row and sha and row['sha256'] and row['sha256'] != sha:
        raise DatabaseError(f'Asset checksum changed; refusing to rewrite its history: {path}')
    asset_id = row['asset_id'] if row else uuid.uuid4().hex
    width, height, bits = metadata.get('width'), metadata.get('height'), None
    if path.is_file():
        try:
            import tifffile
            with tifffile.TiffFile(path) as image:
                page = image.pages[0]
                width, height = page.imagewidth, page.imagelength
                bits = page.bitspersample
        except (OSError, ValueError, IndexError, tifffile.TiffFileError):
            pass
    status = 'completed' if path.is_file() and sha else ('pending' if not path.exists() else 'registered')
    if not row:
        db.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (asset_id, asset_type, parent, job, str(path), path.name, sha, path.suffix.lstrip('.').lower(), width, height, bits,
                    created or now(), date or processing_date(path), status, encode(metadata)))
    else:
        db.execute('''UPDATE assets SET asset_type=CASE WHEN asset_type='external' THEN ? ELSE asset_type END,
                      parent_asset_id=COALESCE(parent_asset_id,?),job_id=COALESCE(job_id,?),sha256=COALESCE(sha256,?),
                      width=COALESCE(?,width),height=COALESCE(?,height),bit_depth=COALESCE(?,bit_depth),status=?,metadata_json=? WHERE asset_id=?''',
                   (asset_type,parent,job,sha,width,height,bits,status,encode(metadata or json.loads(row['metadata_json'])),asset_id))
    return asset_id


def save_job(db, job_id, job_type, payload, output='', parent=None):
    existing = db.execute('SELECT job_type,output_path FROM scan_jobs WHERE job_id=?',(job_id,)).fetchone()
    if existing and (existing['job_type'] != job_type or (existing['output_path'] and output and key(existing['output_path']) != key(output))):
        raise DatabaseError(f'Ambiguous job identity: {job_id}')
    status = payload.get('status', 'running')
    logical = 'partial' if status == 'interrupted' else status
    if logical not in {'pending','running','completed','partial','failed'}:
        raise DatabaseError(f'Invalid job state: {logical}')
    legacy_status = 'interrupted' if logical in {'pending','partial'} else logical
    created = payload.get('created_at') or payload.get('started_at') or now()
    db.execute('''INSERT INTO scan_jobs (job_id,started_at,status,device,output_path,partial_path,settings_json,job_type,
                  parent_job_id,processing_date,processing_status,command,metadata_json,error,finished_at)
                  VALUES (?,?,?,'',?,'',?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,processing_status=excluded.processing_status,
                  finished_at=excluded.finished_at,error=excluded.error,metadata_json=excluded.metadata_json,
                  settings_json=excluded.settings_json,parent_job_id=COALESCE(scan_jobs.parent_job_id,excluded.parent_job_id)''',
               (job_id,created,legacy_status,str(output),encode({'parameters':payload.get('options') or payload.get('parameters') or payload,'cli_configuration':CLI_CONFIG.get() or {}}),job_type,
                parent,processing_date(Path(output or payload.get('source_path') or ''),payload),logical,
                payload.get('command') or CLI_COMMAND.get() or f'photo-utils {job_type}',encode(payload),payload.get('error'),now() if logical in {'completed','partial','failed'} else None))


def put_recipe(db, job, source, output, stage, payload):
    recipe_id = uuid.uuid5(uuid.NAMESPACE_URL, f'{job}:{source}:{output}:{stage}').hex
    db.execute('''INSERT INTO recipes VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(recipe_id) DO UPDATE SET payload_json=excluded.payload_json''',
               (recipe_id,job,source,output,stage,payload.get('created_at') or now(),payload.get('algorithm','unknown'),encode(payload)))


def save_record(path, payload, db=None):
    if db is None:
        with transaction() as connection:
            return save_record(path,payload,connection)
    path = Path(path).resolve()
    kind = 'recipe' if 'recipe_version' in payload else ('split' if 'cards' in payload else 'retouch')
    prior = db.execute('SELECT job_id FROM metadata_records WHERE record_key=?',(str(path),)).fetchone()
    job_id = payload.get('job_id') or (prior[0] if prior else uuid.uuid5(uuid.NAMESPACE_URL,str(path)).hex)
    parent_job = None
    if kind == 'split':
        source_path = Path(payload['source_path'])
        scan = db.execute("SELECT job_id FROM scan_jobs WHERE job_type='scan' AND output_path=?",(key(source_path),)).fetchone()
        parent_job = scan[0] if scan else None
    elif isinstance(payload.get('source_sha256'),dict):
        parents = {row[0] for source_path in payload['source_sha256'] for row in db.execute('SELECT job_id FROM assets WHERE path=? AND job_id IS NOT NULL',(key(source_path),))}
        parent_job = next(iter(parents)) if len(parents)==1 else None
    elif payload.get('source_path'):
        source_row = db.execute('SELECT job_id FROM assets WHERE path=?',(key(payload['source_path']),)).fetchone()
        parent_job = source_row[0] if source_row else None
    if kind == 'recipe' and not payload.get('job_id'):
        # Legacy recipes belong to the enclosing retouch manifest when present.
        matches = []
        for manifest in db.execute("SELECT record_key,job_id,payload_json FROM metadata_records WHERE kind='retouch'"):
            data = json.loads(manifest['payload_json'])
            if any(key(Path(manifest['record_key']).parent/item['relative_output']) == key(payload['output_path']) for item in data.get('files',[])):
                matches.append(manifest['job_id'])
        if len(set(matches))>1:
            raise DatabaseError(f'Ambiguous retouch job for {path}')
        if matches:
            job_id = matches[0]
    if kind == 'recipe' and not payload.get('status'):
        payload = {**payload,'status':'completed' if Path(payload['output_path']).is_file() else 'running'}
    if kind != 'recipe' or not db.execute('SELECT 1 FROM scan_jobs WHERE job_id=?',(job_id,)).fetchone():
        save_job(db,job_id,'split' if kind=='split' else 'retouch',payload,payload.get('output_path',path.parent),parent_job)
    payload = dict(payload)
    payload.setdefault('job_id',job_id)
    if kind == 'split':
        source = asset(db,payload['source_path'],'master',job=parent_job,sha=payload.get('source_sha256'),created=payload.get('created_at'),date=processing_date(path,payload))
        for card in payload['cards']:
            output = path.parent / card['filename']
            result = asset(db,output,'print',source,job_id,card.get('sha256'),card,payload.get('created_at'),processing_date(path,payload))
            put_recipe(db,job_id,source,result,'print',{**payload,'card':card})
    elif kind == 'recipe':
        source = asset(db,payload['source_path'],sha=payload.get('source_sha256'))
        source_date = db.execute('SELECT processing_date FROM assets WHERE asset_id=?',(source,)).fetchone()[0]
        output = Path(payload['output_path'])
        result = asset(db,output,'retouch',source,job_id,payload.get('output_sha256'),payload, payload.get('created_at'),payload.get('scan_date') or source_date)
        put_recipe(db,job_id,source,result,'retouch',payload)
    elif 'files' in payload:
        for source_path,sha in payload.get('source_sha256',{}).items():
            asset(db,source_path,sha=sha)
        for item in payload['files']:
            source = asset(db,item['source_path'],sha=item.get('source_sha256'))
            source_date = db.execute('SELECT processing_date FROM assets WHERE asset_id=?',(source,)).fetchone()[0]
            asset(db,path.parent/item['relative_output'],'retouch',source,job_id,item.get('output_sha256'),item,date=payload.get('scan_date') or source_date)
    elif payload.get('source_path'):
        source = asset(db,payload['source_path'],sha=payload.get('source_sha256'))
        if payload.get('output_path'):
            asset(db,payload['output_path'],'retouch',source,job_id,payload.get('output_sha256'),payload,date=processing_date(path,payload))
    # Completed jobs must reference published outputs; missing outputs degrade to partial.
    missing = db.execute("SELECT path FROM assets WHERE job_id=? AND asset_type IN ('master','print','retouch')",(job_id,)).fetchall()
    if payload.get('status') == 'completed' and any(not Path(row[0]).is_file() for row in missing):
        db.execute("UPDATE scan_jobs SET status='interrupted',processing_status='partial',error='Output file missing' WHERE job_id=?",(job_id,))
    if payload.get('status')=='failed' and db.execute("SELECT 1 FROM assets WHERE job_id=? AND asset_type IN ('print','retouch') AND status='completed' LIMIT 1",(job_id,)).fetchone():
        db.execute("UPDATE scan_jobs SET processing_status='partial' WHERE job_id=?",(job_id,))
    db.execute('''INSERT INTO metadata_records VALUES (?,?,?,?,?) ON CONFLICT(record_key) DO UPDATE SET
                  job_id=excluded.job_id,payload_json=excluded.payload_json,updated_at=excluded.updated_at''',
               (str(path),kind,job_id,encode(payload),now()))
    return job_id


def sync_scan(db, job_id):
    row = db.execute('SELECT * FROM scan_jobs WHERE job_id=?',(job_id,)).fetchone()
    if row is None:
        return
    payload = dict(row)
    settings = json.loads(row['settings_json'])
    logical = 'partial' if row['status']=='interrupted' else row['status']
    if logical=='completed' and not Path(row['output_path']).is_file():
        logical = 'partial'
    date = settings.get('scan_date') or row['started_at'][:10].replace('-','')
    db.execute("UPDATE scan_jobs SET processing_status=?,processing_date=?,command=CASE WHEN command='' THEN ? ELSE command END WHERE job_id=?",
               (logical,date,CLI_COMMAND.get() or 'photo-utils scan',job_id))
    if row['sha256'] or row['status']=='completed':
        asset(db,row['output_path'],'master',job=job_id,sha=row['sha256'],metadata=settings,created=row['started_at'],date=date)


def import_ledger(db, root):
    old = Path(root)/'.photo-utils-naming.sqlite3'
    if old.is_file():
        with closing(raw_connect(old,readonly=True)) as legacy:
            for row in legacy.execute('SELECT date,number FROM daily_ids'):
                db.execute('''INSERT INTO daily_ids VALUES (?,?,?) ON CONFLICT(root,date) DO UPDATE SET number=max(number,excluded.number)''',(key(root),row[0],row[1]))
            if legacy.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_sources'").fetchone():
                for row in legacy.execute('SELECT source,date,number FROM legacy_sources'):
                    prior = db.execute('SELECT date,number FROM legacy_sources WHERE source=?',(row[0],)).fetchone()
                    if prior and tuple(prior)!=tuple(row)[1:]:
                        raise DatabaseError(f'Ambiguous legacy naming identity: {row[0]}')
                    db.execute('INSERT OR IGNORE INTO legacy_sources VALUES (?,?,?,?)',(row[0],key(root),row[1],row[2]))


def reserve(root, date, source=None, dry_run=False):
    root = Path(root).resolve()
    if dry_run:
        location = database_path()
        if not location.exists():
            old = root / '.photo-utils-naming.sqlite3'
            if old.exists():
                with closing(raw_connect(old,readonly=True)) as db:
                    if source and db.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_sources'").fetchone():
                        row = db.execute('SELECT date,number FROM legacy_sources WHERE source=?',(key(source),)).fetchone()
                        if row:
                            return row[0],row[1]
                    row = db.execute('SELECT number FROM daily_ids WHERE date=?',(date,)).fetchone()
                    return date,row[0]+1 if row else 1
            return date,1
        with closing(raw_connect(location,readonly=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='daily_ids'").fetchone():
                return date,1
            if source:
                row = db.execute('SELECT date,number FROM legacy_sources WHERE source=?',(key(source),)).fetchone()
                if row:
                    return row[0],row[1]
            row = db.execute('SELECT number FROM daily_ids WHERE root=? AND date=?',(str(root),date)).fetchone()
            return date,row[0]+1 if row else 1
    root.mkdir(parents=True, exist_ok=True)
    binding = root / '.photo-utils-database'
    with (root / '.photo-utils-allocation.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        if binding.exists() and binding.read_text().strip() != str(database_path()):
            raise DatabaseError('This scan root is bound to another job database: ' + binding.read_text().strip())
        if not binding.exists():
            with binding.open('x') as stream:
                stream.write(str(database_path()) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
    with transaction() as db:
        import_ledger(db,root)
        if source:
            row = db.execute('SELECT date,number FROM legacy_sources WHERE source=?',(key(source),)).fetchone()
            if row:
                return row[0],row[1]
        row = db.execute('SELECT number FROM daily_ids WHERE root=? AND date=?',(str(root),date)).fetchone()
        number = row[0]+1 if row else 1
        db.execute('INSERT OR REPLACE INTO daily_ids VALUES (?,?,?)',(str(root),date,number))
        if source:
            db.execute('INSERT INTO legacy_sources VALUES (?,?,?,?)',(key(source),str(root),date,number))
        return date,number


def query_jobs(date=None, job_type=None, status=None, limit=20):
    with closing(connect()) as db:
        conditions, values = [], []
        for column,value in [('processing_date',date),('job_type',job_type),('processing_status',status)]:
            if value:
                conditions.append(column+'=?')
                values.append(value)
        sql = 'SELECT * FROM scan_jobs' + (' WHERE '+' AND '.join(conditions) if conditions else '')
        rows = db.execute(sql+' ORDER BY julianday(started_at) DESC,started_at DESC LIMIT ?', values+[limit]).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['asset_counts'] = dict(db.execute('SELECT asset_type,count(*) FROM assets WHERE job_id=? GROUP BY asset_type',(row['job_id'],)).fetchall())
            master = db.execute("""WITH RECURSIVE lineage AS (
                SELECT asset_id,parent_asset_id,asset_type,filename FROM assets WHERE job_id=?
                UNION SELECT a.asset_id,a.parent_asset_id,a.asset_type,a.filename FROM assets a JOIN lineage l ON a.asset_id=l.parent_asset_id)
                SELECT filename FROM lineage WHERE asset_type='master' LIMIT 1""",(row['job_id'],)).fetchone()
            item['master_filename'] = master[0] if master else ''
            result.append(item)
        return result


def job_details(job_id):
    with closing(connect()) as db:
        row = db.execute('SELECT * FROM scan_jobs WHERE job_id=?',(job_id,)).fetchone()
        if not row:
            raise DatabaseError('Unknown job ID: '+job_id)
        assets = [dict(item) for item in db.execute("""WITH RECURSIVE ancestors AS (
            SELECT * FROM assets WHERE job_id=? OR asset_id IN (SELECT source_asset_id FROM recipes WHERE job_id=?)
            UNION SELECT a.* FROM assets a JOIN ancestors p ON a.asset_id=p.parent_asset_id),
            family AS (SELECT * FROM ancestors UNION SELECT a.* FROM assets a JOIN family p ON a.parent_asset_id=p.asset_id)
            SELECT * FROM family ORDER BY processing_date,path""",(job_id,job_id))]
        asset_ids = [item['asset_id'] for item in assets]
        placeholders = ','.join('?' for _ in asset_ids) or 'NULL'
        recipes = [dict(item) for item in db.execute(f'SELECT * FROM recipes WHERE job_id=? OR output_asset_id IN ({placeholders}) ORDER BY julianday(created_at),created_at', [job_id]+asset_ids)]
        records = [dict(row) for row in db.execute('SELECT * FROM metadata_records WHERE job_id=?',(job_id,))]
        def unpack(item):
            return {k[:-5] if k.endswith('_json') else k:json.loads(v) if k.endswith('_json') else v for k,v in item.items()}
        return {'job':unpack(dict(row)),'assets':[unpack(item) for item in assets],
                'recipes':[unpack(item) for item in recipes], 'manifests':[unpack(item) for item in records],
                'stored_json':{item['record_key']:item['payload_json'] for item in records}}


def query_assets(date=None, stage=None, status=None):
    with closing(connect()) as db:
        conditions, values = [], []
        for column,value in [('processing_date',date),('asset_type',stage),('status',status)]:
            if value:
                conditions.append(column+'=?')
                values.append(value)
        return [dict(row) for row in db.execute('SELECT * FROM assets'+(' WHERE '+' AND '.join(conditions) if conditions else '')+' ORDER BY processing_date,path',values)]


def history(asset_id):
    with closing(connect()) as db:
        row = db.execute('SELECT * FROM assets WHERE asset_id=?',(asset_id,)).fetchone()
        if not row:
            raise DatabaseError('Unknown asset ID: '+asset_id)
        lineage = []
        seen = set()
        while row:
            if row['asset_id'] in seen:
                raise DatabaseError('Cycle in asset lineage.')
            seen.add(row['asset_id'])
            lineage.append(dict(row))
            row = db.execute('SELECT * FROM assets WHERE asset_id=?',(row['parent_asset_id'],)).fetchone() if row['parent_asset_id'] else None
        recipes = [dict(item) for item in db.execute('SELECT * FROM recipes WHERE source_asset_id=? OR output_asset_id=? ORDER BY julianday(created_at),created_at,recipe_id',(asset_id,asset_id))]
        for item in recipes:
            item['payload'] = json.loads(item.pop('payload_json'))
        children = [dict(item) for item in db.execute('SELECT * FROM assets WHERE parent_asset_id=?',(asset_id,))]
        return {'lineage':list(reversed(lineage)), 'children':children, 'recipes':recipes}


def check_database(verify_checksums=False):
    with closing(connect()) as db:
        integrity = [row[0] for row in db.execute('PRAGMA integrity_check')]
        foreign_keys = [tuple(row) for row in db.execute('PRAGMA foreign_key_check')]
        missing, changed = [], []
        for row in db.execute('SELECT asset_id,path,sha256,status,job_id FROM assets'):
            if not Path(row['path']).is_file():
                missing.append(dict(row))
            elif verify_checksums and row['sha256'] and digest(row['path']) != row['sha256']:
                changed.append(dict(row))
        return {'schema_version':db.execute('PRAGMA user_version').fetchone()[0],
                'integrity':integrity,'foreign_key_errors':foreign_keys,
                'missing_files':missing,'changed_files':changed,
                'database_ok':integrity==['ok'] and not foreign_keys}
