"""Local, durable scan identities and readable stage names."""
from pathlib import Path
import re
from . import database

PATTERN = re.compile(r"^(\d{8})-(\d{3,})(?:-(\d{2,}))?-(master|print|retouch)(?:-v(\d{2,}))?\.tif$")


def identity(path: Path):
    match = PATTERN.fullmatch(path.name)
    if not match:
        return None
    date, number, print_number, stage, version = match.groups()
    return date, int(number), int(print_number) if print_number else None, stage


def master_id(date: str, number: int) -> str:
    return f"{date}-{number:03d}"


def allocate(root: Path, date: str) -> int:
    """Reserve permanently, including failed jobs; SQLite serializes writers."""
    return database.reserve(root,date)[1]


def day_directory(source: Path) -> Path:
    parsed = identity(source)
    if parsed is None:
        raise ValueError("Source has no scan identity")
    parent = source.parent.parent if source.parent.name in {"masters", "prints", "retouches"} else source.parent
    return parent if parent.name == parsed[0] else parent / parsed[0]


def tracking(source: Path, stage: str) -> dict:
    parsed = identity(source)
    if not parsed:
        return {}
    date, number, print_number, _ = parsed
    parent = master_id(date, number)
    if stage == "retouch" and print_number is not None:
        parent += f"-{print_number:02d}"
    return {"scan_date": date, "master_id": master_id(date, number), "parent_id": parent, "processing_stage": stage}


def serialized_derivatives(function):
    """Serialize recipe/manifest updates and version selection for one scan day."""
    import functools
    import fcntl
    @database.scoped_state
    @functools.wraps(function)
    def wrapped(source, *args, **kwargs):
        path = Path(source).expanduser().resolve()
        if path.is_dir():
            candidate = next((item for item in path.rglob("*.tif") if identity(item)), None)
            if candidate is not None:
                path = candidate
        parsed = identity(path)
        day = day_directory(path) if parsed else (path.parent if path.is_file() or path.name == "prints" else None)
        if kwargs.get("dry_run"):
            return function(source, *args, **kwargs)
        if day is None:
            day = database.state_dir()
            return function(source, *args, **kwargs)
        day.mkdir(parents=True, exist_ok=True)
        with (day / ".derivatives.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            return function(source, *args, **kwargs)
    return wrapped


def existing_master(source: Path, dry_run: bool = False):
    """Assign an identity without renaming a legacy sheet; remember its provenance."""
    from datetime import datetime
    match = re.search(r"LiDE400-(\d{8})T", source.name)
    date = match[1] if match else datetime.fromtimestamp(source.stat().st_mtime).astimezone().strftime("%Y%m%d")
    root = source.parent.parent if re.fullmatch(r"\d{8}", source.parent.name) else source.parent
    date, number = database.reserve(root,date,source,dry_run)
    return (date, number, None, "master"), root / date
