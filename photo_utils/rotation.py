"""Preserve originals and publish full-resolution quarter-turn TIFF derivatives."""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any
from . import database
from .retouch import resolve_magick, resolve_exiftool, EXIFTOOL_METADATA_ARGS
from .similarity_native import SimilarityError


def command(args: list[str]) -> str:
    result = subprocess.run(args,capture_output=True,text=True,timeout=180)
    if result.returncode: raise SimilarityError('Rotation failed: '+result.stderr.strip())
    return result.stdout


def publish_rotations(result: dict[str, Any]) -> None:
    for image in result['images']:
        rotation = image.get('rotation',{})
        q = rotation.get('quarter_turns_clockwise',0)
        if not q: continue
        source = Path(image['path'])
        if database.digest(source) != image['sha256']: raise SimilarityError('Changed rotation source')
        destination = (source.parent/'rotated'/(source.name+'.upright.tif')).resolve()
        with database.transaction() as db:
            previous = db.execute('SELECT * FROM assets WHERE path=?',(str(destination),)).fetchone()
            if previous:
                meta = json.loads(previous['metadata_json'])
                if (not destination.is_file() or database.digest(destination)!=previous['sha256']
                        or meta.get('source_sha256')!=image['sha256'] or meta.get('quarter_turns_clockwise')!=q):
                    raise SimilarityError('Existing rotated derivative changed or uses different settings: '+str(destination))
                rotation['output'] = str(destination)
                continue
        destination.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.rotation-',dir=destination.parent) as work:
            temporary = Path(work)/'upright.tif'
            magick,exiftool = str(resolve_magick()),str(resolve_exiftool())
            command([magick,str(source),'-auto-orient','-rotate',str(q*90),'-compress','zip',str(temporary)])
            command([exiftool,'-TagsFromFile',str(source),*EXIFTOOL_METADATA_ARGS,'--Orientation',
                     '-Orientation#=1','-overwrite_original',str(temporary)])
            # Verify dimensions, orientation and retained sample depth against an EXIF-upright source.
            before=command([magick,str(source),'-auto-orient','-format','%w %h %z','info:']).split()
            after=command([magick,str(temporary),'-format','%w %h %z','info:']).split()
            expected=[before[1],before[0],before[2]] if q%2 else before
            if after!=expected: raise SimilarityError('Rotated derivative geometry/depth verification failed')
            if database.digest(source)!=image['sha256']: raise SimilarityError('Source changed during rotation')
            sha=database.digest(temporary)
            with database.transaction() as db:
                parent=database.asset(db,source,job=result['job_id'],sha=image['sha256'])
                row=db.execute('SELECT processing_date FROM assets WHERE asset_id=?',(parent,)).fetchone()
                metadata={'source_sha256':image['sha256'],'quarter_turns_clockwise':q,
                          'evidence':rotation,'status':'completed','algorithm':'quarter-turn-v1'}
                # No replacement: an unexpected file is never adopted.
                os.link(temporary,destination)
                child=database.asset(db,destination,parent=parent,job=result['job_id'],sha=sha,
                                     metadata=metadata,date=row['processing_date'])
                db.execute('INSERT INTO recipes VALUES (?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex,result['job_id'],parent,child,'orientation',database.now(),
                     'quarter-turn-v1',database.encode(metadata)))
            rotation['output']=str(destination)
