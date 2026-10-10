"""Compact metadata browsing and explicit exports for the existing CLI."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import os
import tempfile
from argparse import Namespace
from typing import Any, Optional

from . import database as store


def date_argument(value: str) -> str:
    import argparse
    try:
        parsed = datetime.strptime(value,'%Y%m%d')
        if parsed.strftime('%Y%m%d') != value:
            raise ValueError()
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use a valid YYYYMMDD date.') from exc
    return value


def show_json(value: Any) -> None:
    print(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True))


def list_jobs(date: Optional[str] = None, job_type: Optional[str] = None, status: Optional[str] = None, limit: int = 20) -> None:
    if limit < 1:
        raise store.DatabaseError('--limit must be positive')
    rows = store.query_jobs(date,job_type,status,limit)
    print('JOB ID                            DATE/TIME                  TYPE     STATUS     MASTER / PRINTS / RETOUCHES')
    for row in rows:
        counts = row['asset_counts']
        timestamp = datetime.fromisoformat(row['started_at'].replace('Z','+00:00')).astimezone().isoformat(timespec='seconds')
        print(f"{row['job_id']:32}  {timestamp:25}  {row['job_type']:7}  {row['processing_status']:9}  {row['master_filename']} / {counts.get('print',0)} / {counts.get('retouch',0)}")
    if not rows:
        print('No matching jobs.')


def list_assets(date: Optional[str] = None, stage: Optional[str] = None, status: Optional[str] = None) -> None:
    rows = store.query_assets(date,stage,status)
    by_id = {row['asset_id']:row for row in store.query_assets()}
    def root(row: dict[str, Any]) -> str:
        seen: set[str] = set()
        while row.get('parent_asset_id') in by_id:
            if row['asset_id'] in seen:
                raise store.DatabaseError('Cycle in asset lineage')
            seen.add(row['asset_id'])
            row = by_id[row['parent_asset_id']]
        return row['asset_id']
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(root(row),[]).append(row)
    for group,items in groups.items():
        print(f"\n{by_id[group]['filename']} [{group}]")
        for row in items:
            print(f"  {row['asset_id']}  {row['asset_type']:8} {row['status']:10} {row['path']}  parent={row['parent_asset_id'] or '-'}")
    if not groups:
        print('No matching assets.')


def recipe_show(asset_id: str, recipe_id: Optional[str] = None) -> None:
    rows = [row for row in store.history(asset_id)['recipes'] if row['output_asset_id']==asset_id]
    if recipe_id:
        rows = [row for row in rows if row['recipe_id']==recipe_id]
    if not rows:
        raise store.DatabaseError('No matching recipe for this asset.')
    for row in rows:
        print(f"Recipe {row['recipe_id']}  {row['created_at']}  {row['stage']}  {row['algorithm']}")
        show_json(row['payload'])


def export_job(job_id: str, output: Optional[Path] = None) -> None:
    value = store.job_details(job_id)
    data = json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    if output is None:
        print(data,end='')
        return
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    handle,temporary = tempfile.mkstemp(prefix='.metadata-export-',dir=output.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf-8') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary,output)
    except FileExistsError as exc:
        raise store.DatabaseError(f'Refusing to overwrite export: {output}') from exc
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(f'Exported: {output}')


def dispatch(args: Namespace) -> int:
    if args.command=='jobs':
        list_jobs(args.date,args.type,args.status,args.limit)
    elif args.command=='assets':
        list_assets(args.date,args.stage,args.status)
    elif args.command=='job':
        if args.action=='show':
            show_json(store.job_details(args.job_id))
        else:
            export_job(args.job_id,args.output)
    elif args.command=='recipe':
        recipe_show(args.asset_id,args.recipe_id)
    elif args.command=='history':
        show_json(store.history(args.asset_id))
    elif args.command=='db':
        if args.action=='check':
            value = store.check_database(args.checksums)
            print('Database integrity: '+('OK' if value['database_ok'] else 'FAILED'))
            print(f"Missing image files: {len(value['missing_files'])}; changed checksums: {len(value['changed_files'])}")
            show_json(value)
            return 0 if value['database_ok'] and not value['missing_files'] and not value['changed_files'] else 1
    return 0


def menu() -> None:
    while True:
        print('\nHistory & Database\n  1) List jobs by date\n  2) Browse recent jobs\n  3) View job details\n  4) Browse assets by date\n  5) View processing recipe\n  6) View asset history\n  7) Export job data\n  8) Database diagnostics\n  9) Back')
        choice = input('Select [9]: ').strip() or '9'
        today = datetime.now().astimezone().strftime('%Y%m%d')
        try:
            if choice=='9':
                return
            if choice in {'1','4'}:
                date = date_argument(input(f'Date [{today}]: ').strip() or today)
                if choice=='1':
                    status = input('Status filter (blank for all): ').strip() or None
                    job_type = input('Stage/type filter (blank for all): ').strip() or None
                    list_jobs(date,job_type,status)
                else:
                    stage = input('Stage filter (blank for all): ').strip() or None
                    status = input('Status filter (blank for all): ').strip() or None
                    list_assets(date,stage,status)
            elif choice=='2':
                list_jobs()
            elif choice=='3':
                show_json(store.job_details(input('Job ID: ').strip()))
            elif choice=='5':
                asset_id = input('Asset ID: ').strip()
                rows = [r for r in store.history(asset_id)['recipes'] if r['output_asset_id']==asset_id]
                for row in rows:
                    print(row['recipe_id'],row['created_at'],row['algorithm'])
                recipe_show(asset_id,input('Recipe ID (blank for all): ').strip() or None)
            elif choice=='6':
                show_json(store.history(input('Asset ID: ').strip()))
            elif choice=='7':
                job_id = input('Job ID: ').strip()
                destination = input('Export filename (blank for stdout): ').strip()
                export_job(job_id,Path(destination) if destination else None)
            elif choice=='8':
                result = store.check_database()
                print('Database integrity: '+('OK' if result['database_ok'] else 'FAILED'))
                show_json(result)
            else:
                print('Choose 1 through 9.')
        except (store.DatabaseError,ValueError,OSError) as exc:
            print(f'Error: {exc}')
