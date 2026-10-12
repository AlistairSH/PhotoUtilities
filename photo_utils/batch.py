"""Existing folder workflow: oriented analysis, grouping/focus, optional TIFF edits."""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Sequence
from .similarity import collect_images,find_similar
from .similarity_native import SimilarityError
from .retouch import retouch,RetouchOptions


def process_batch(targets: Sequence[Path], *, recursive: bool = False, report: Optional[Path] = None,
                  profile: str = 'none',dry_run: bool = False,no_db: bool = False) -> Optional[Path]:
    if profile not in ('none','polaroid'):raise SimilarityError('Unsupported folder edit profile.')
    paths=collect_images(targets,recursive,skip_generated=True)
    # Do not recursively ingest already-generated edits, scanner masters or
    # soft archives when the root of the photo collection is supplied.
    filtered: list[Path]=[]
    for path in paths:
        if any(part in ('Blurry','retouches','masters') for part in path.parts):continue
        if 'retouched' in path.stem or '-retouch' in path.stem:continue
        filtered.append(path)
    if not filtered:raise SimilarityError('No source images remain after excluding masters, retouches and archives.')
    if profile=='polaroid' and any(path.suffix.lower() not in ('.tif','.tiff') for path in filtered):
        raise SimilarityError('The existing Polaroid edit recipe supports TIFF only; use --retouch none for JPEG/HEIC or select TIFF inputs.')
    if profile!='none' and no_db:raise SimilarityError('Edits require SQLite history; --no-db is analysis-only.')
    print('Folder workflow: apply embedded orientation during decoding, group similar originals, flag focus for review, then requested TIFF edits.')
    destination=report
    if destination is None:
        destination=targets[0].expanduser().resolve()
        destination=(destination if destination.is_dir() else destination.parent)/'review.html'
        counter=1;candidate=destination
        while candidate.exists():
            counter+=1;candidate=destination.with_name(f'review-v{counter:02d}.html')
        destination=candidate
    result=find_similar(filtered,report=destination,focus=True,dry_run=dry_run,no_db=no_db)
    if profile=='polaroid':
        for path in filtered:retouch(path,options=RetouchOptions(profile=profile),dry_run=dry_run)
    return result
