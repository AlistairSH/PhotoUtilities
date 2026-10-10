from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional, Sequence

from .naming import allocate, master_id
from . import database


class ScanError(RuntimeError):
    pass


MODES = {
    "48-bit-color": "48 bits color",
    "color": "Color",
    "gray": "Gray",
    "16-bit-gray": "16 bits gray",
}
RESOLUTIONS = (75, 150, 300, 600, 1200, 2400, 4800)
SCANNER_PATTERN = re.compile(r"^\s*device\s+[`']([^`']+)[`']\s+is\s+(.+)$", re.IGNORECASE)
TIFF_HEADERS = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def default_root() -> Path:
    return Path.home() / "Documents" / "PhotoScans"


def default_scan_folder() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d")


def default_state_dir() -> Path:
    return database.state_dir()


def resolve_scanimage() -> Path:
    configured = os.environ.get("PHOTO_UTILITIES_SCANIMAGE")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.absolute()
        raise ScanError(
            f"PHOTO_UTILITIES_SCANIMAGE is not an executable file: {candidate}"
        )
    located = shutil.which("scanimage")
    candidates = [Path(located)] if located else []
    candidates.extend((Path("/opt/homebrew/bin/scanimage"), Path("/usr/local/bin/scanimage")))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.absolute()
    raise ScanError(
        "Cannot find scanimage. Install sane-backends with Homebrew, add it to "
        "PATH, or set PHOTO_UTILITIES_SCANIMAGE to its executable path."
    )


def parse_scanner_list(output: str) -> list[tuple[str, str]]:
    devices: list[tuple[str, str]] = []
    for line in output.splitlines():
        match = SCANNER_PATTERN.match(line)
        if match:
            devices.append((match.group(1), match.group(2)))
    return devices


def list_scanners(scanimage: Path) -> list[tuple[str, str]]:
    try:
        result = subprocess.run(
            [str(scanimage), "--list-devices"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ScanError(f"Could not run scanimage: {exc}") from exc
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode:
        detail = output.strip() or f"exit status {result.returncode}"
        raise ScanError(f"Scanner discovery failed: {detail}")
    return parse_scanner_list(output)


def select_scanner(
    devices: Sequence[tuple[str, str]], requested_device: Optional[str] = None
) -> tuple[str, str]:
    if requested_device:
        for device_id, description in devices:
            if device_id == requested_device:
                return device_id, description
        raise ScanError(
            f"Requested scanner {requested_device!r} was not found. "
            "Check the device name with `scanimage -L`."
        )

    lide_devices = [
        device for device in devices if "lide 400" in device[1].lower()
    ]
    if len(lide_devices) == 1:
        return lide_devices[0]
    if len(lide_devices) > 1:
        names = ", ".join(device_id for device_id, _ in lide_devices)
        raise ScanError(
            f"More than one LiDE 400 was detected ({names}); specify --device."
        )
    raise ScanError(
        "No Canon LiDE 400 was found. Check the USB connection and run "
        "`scanimage -L` and `sane-find-scanner -q`."
    )


def validate_folder_name(folder: str) -> str:
    if (
        not folder.strip()
        or folder in {".", ".."}
        or Path(folder).name != folder
        or "/" in folder
        or "\\" in folder
        or "\x00" in folder
    ):
        raise ScanError("--folder must be one folder name, not a path.")
    return folder


def make_output_name(resolution: int, mode: str, job_id: str) -> str:
    return f"{job_id}-master.tif"


def build_scan_command(
    scanimage: Path,
    device_id: str,
    output_path: Path,
    resolution: int,
    mode: str,
    *,
    progress: bool = False,
    dont_scan: bool = False,
) -> list[str]:
    if mode not in MODES:
        raise ScanError(f"Unsupported scan mode: {mode}")
    if resolution not in RESOLUTIONS:
        raise ScanError(f"Unsupported scan resolution: {resolution}")
    command = [
        str(scanimage),
        "--device-name",
        device_id,
        "--source",
        "Flatbed",
        "--mode",
        MODES[mode],
        "--resolution",
        str(resolution),
        "--format=tiff",
        "--output-file",
        str(output_path),
    ]
    if progress:
        command.append("--progress")
    if dont_scan:
        command.append("--dont-scan")
    return command


def is_tiff(path: Path) -> bool:
    try:
        with path.open("rb") as image_file:
            return image_file.read(4) in TIFF_HEADERS
    except FileNotFoundError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_visible(path: Path) -> None:
    hidden_flag = getattr(stat, "UF_HIDDEN", 0)
    if not hidden_flag:
        return
    try:
        flags = path.stat().st_flags
        if flags & hidden_flag:
            os.chflags(path, flags & ~hidden_flag)
        if path.stat().st_flags & hidden_flag:
            raise ScanError(f"Output file is still marked hidden: {path}")
    except OSError as exc:
        raise ScanError(f"Could not clear the hidden flag on {path}: {exc}") from exc


def connect_database(path: Path) -> sqlite3.Connection:
    try:
        return database.connect(path)
    except (sqlite3.Error, OSError, database.DatabaseError) as exc:
        raise ScanError(f"Could not open the local job database: {exc}") from exc


@contextmanager
def scan_lock(state_dir: Path) -> Generator[None, None, None]:
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        lock_file = (state_dir / "scan.lock").open("a")
    except OSError as exc:
        raise ScanError(f"Could not create the scan lock: {exc}") from exc
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ScanError("Another PhotoUtilities scan is already running.") from exc
        except OSError as exc:
            raise ScanError(f"Could not lock scan state directory: {exc}") from exc
        yield
    finally:
        lock_file.close()


def mark_abandoned_jobs_interrupted(connection: sqlite3.Connection) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    running = connection.execute(
        "SELECT job_id, output_path FROM scan_jobs WHERE status = 'running' AND job_type = 'scan'"
    ).fetchall()
    for job_id, output_path in running:
        final_path = Path(output_path)
        try:
            size_bytes = final_path.stat().st_size
            valid_output = size_bytes > 4 and is_tiff(final_path)
            digest = sha256_file(final_path) if valid_output else None
        except FileNotFoundError:
            valid_output = False
            size_bytes = None
            digest = None
        except OSError as exc:
            raise ScanError(
                f"Could not recover prior scan job {job_id}: {exc}"
            ) from exc
        if valid_output:
            connection.execute(
                """
                UPDATE scan_jobs
                SET status = 'completed', finished_at = ?, sha256 = ?, size_bytes = ?,
                    error = 'Recovered completed output after interrupted state update.'
                WHERE job_id = ?
                """,
                (
                    now,
                    digest,
                    size_bytes,
                    job_id,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE scan_jobs SET status = 'interrupted', finished_at = ?,
                    error = 'Previous process ended before the scan completed.'
                WHERE job_id = ?
                """,
                (now, job_id),
            )
    for job_id, _ in running:
        database.sync_scan(connection, job_id)
    connection.commit()


def update_job(
    connection: sqlite3.Connection,
    job_id: str,
    status: str,
    *,
    sha256: Optional[str] = None,
    size_bytes: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    connection.execute(
        """
        UPDATE scan_jobs
        SET status = ?, finished_at = ?, sha256 = ?, size_bytes = ?, error = ?
        WHERE job_id = ?
        """,
        (status, finished_at, sha256, size_bytes, error, job_id),
    )
    database.sync_scan(connection, job_id)
    connection.commit()


@database.scoped_state
def run_scan(
    *,
    folder: str,
    root: Path,
    state_dir: Path,
    resolution: int = 600,
    mode: str = "48-bit-color",
    requested_device: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[Path]:
    validate_folder_name(folder)
    initiated_at = datetime.now().astimezone()
    scan_date = initiated_at.strftime("%Y%m%d")
    if folder != scan_date:
        print("--folder is deprecated; using the scan initiation date " + scan_date + ".")
    if mode not in MODES:
        raise ScanError(f"Unsupported scan mode: {mode}")
    if resolution not in RESOLUTIONS:
        raise ScanError(f"Unsupported scan resolution: {resolution}")

    scanimage = resolve_scanimage()
    device_id, description = select_scanner(
        list_scanners(scanimage), requested_device
    )
    job_id = uuid.uuid4().hex
    destination = root.expanduser().resolve() / scan_date / "masters"
    output_path = destination / make_output_name(resolution, mode, master_id(scan_date, 1))
    partial_path = destination / f"{output_path.stem}.partial-{job_id}.tif"
    preflight = build_scan_command(
        scanimage,
        device_id,
        output_path,
        resolution,
        mode,
        dont_scan=True,
    )
    try:
        result = subprocess.run(preflight, check=False)
    except OSError as exc:
        raise ScanError(f"Could not validate scanner settings: {exc}") from exc
    if result.returncode:
        raise ScanError(
            "The scanner rejected the requested settings during the no-scan "
            f"preflight (exit status {result.returncode})."
        )

    if dry_run:
        actual = build_scan_command(
            scanimage,
            device_id,
            partial_path,
            resolution,
            mode,
            progress=True,
        )
        print("Dry run: scanner settings validated; no scan or files were created.")
        print(f"Scanner: {description} ({device_id})")
        print(f"Output pattern: {destination / (scan_date + '-NNN-master.tif')}")
        print("The next ID is reserved only when acquisition starts.")
        print(f"Command: {shlex.join(actual)}")
        return None

    try:
        for stage in ("masters", "prints", "retouches"):
            (destination.parent / stage).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScanError(f"Could not create scan destination {destination}: {exc}") from exc
    database_path = state_dir.expanduser() / "jobs.sqlite3"
    with scan_lock(state_dir.expanduser()):
        connection = connect_database(database_path)
        try:
            mark_abandoned_jobs_interrupted(connection)
            number = allocate(root.expanduser().resolve(), scan_date)
            readable_id = master_id(scan_date, number)
            output_path = destination / make_output_name(resolution, mode, readable_id)
            partial_path = destination / f"{output_path.stem}.partial-{job_id}.tif"
            try:
                version_result = subprocess.run(
                    [str(scanimage), "--version"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                raise ScanError(f"Could not read scanimage version: {exc}") from exc
            if version_result.returncode:
                detail = version_result.stderr.strip() or "unknown error"
                raise ScanError(f"Could not read scanimage version: {detail}")
            version = version_result.stdout.strip()
            settings = {
                "scanimage_version": version,
                "master_id": readable_id,
                "scan_date": scan_date,
                "processing_stage": "master",
                "device": device_id,
                "resolution_dpi": resolution,
                "mode": MODES[mode],
                "format": "tiff",
                "source": "Flatbed",
            }
            started_at = initiated_at.isoformat(timespec="seconds")
            connection.execute(
                """
                INSERT INTO scan_jobs
                    (job_id, started_at, status, device, output_path, partial_path,
                     settings_json)
                VALUES (?, ?, 'running', ?, ?, ?, ?)
                """,
                (
                    job_id,
                    started_at,
                    device_id,
                    str(output_path),
                    str(partial_path),
                    json.dumps(settings, sort_keys=True),
                ),
            )
            database.sync_scan(connection, job_id)
            connection.commit()

            command = build_scan_command(
                scanimage,
                device_id,
                partial_path,
                resolution,
                mode,
                progress=True,
            )
            print(f"Scanning {description} to {output_path}", flush=True)
            try:
                scan_result = subprocess.run(command, check=False)
            except KeyboardInterrupt:
                update_job(
                    connection,
                    job_id,
                    "interrupted",
                    error=f"Interrupted; any partial data remains at {partial_path}.",
                )
                raise
            except OSError as exc:
                update_job(connection, job_id, "failed", error=str(exc))
                raise ScanError(f"Could not start scanimage: {exc}") from exc

            if scan_result.returncode:
                message = (
                    f"scanimage exited with status {scan_result.returncode}; "
                    f"any partial data remains at {partial_path}."
                )
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message)
            try:
                size_bytes = partial_path.stat().st_size if is_tiff(partial_path) else 0
            except OSError as exc:
                message = f"Could not validate scan output {partial_path}: {exc}"
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message) from exc
            if size_bytes <= 4:
                message = (
                    "scanimage reported success but did not produce a valid TIFF; "
                    f"any partial data remains at {partial_path}."
                )
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message)

            try:
                ensure_visible(partial_path)
            except ScanError as exc:
                message = (
                    f"Could not make the completed scan visible; scan data remains "
                    f"at {partial_path}: {exc}"
                )
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message) from exc

            try:
                digest = sha256_file(partial_path)
            except OSError as exc:
                message = f"Could not checksum scan output {partial_path}: {exc}"
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message) from exc
            try:
                os.link(partial_path, output_path)
            except FileExistsError as exc:
                message = (
                    f"Refusing to overwrite existing output {output_path}; "
                    f"scan data remains at {partial_path}."
                )
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message) from exc
            except OSError as exc:
                message = (
                    f"Could not publish the completed scan at {output_path}: {exc}. "
                    f"Scan data remains at {partial_path}."
                )
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message) from exc
            try:
                ensure_visible(output_path)
            except ScanError as exc:
                message = (
                    f"Could not ensure the published scan is visible at "
                    f"{output_path}: {exc}"
                )
                update_job(connection, job_id, "failed", error=message)
                raise ScanError(message) from exc
            try:
                partial_path.unlink()
            except OSError as exc:
                print(
                    f"Warning: the completed scan is safe at {output_path}, but "
                    f"the temporary hard link remains at {partial_path}: {exc}",
                    file=sys.stderr,
                )
            update_job(
                connection,
                job_id,
                "completed",
                sha256=digest,
                size_bytes=size_bytes,
            )
            print(f"Saved:   {output_path}")
            print(f"SHA-256: {digest}")
            print(f"Job ID:  {job_id}")
            return output_path
        except KeyboardInterrupt:
            raise
        except ScanError:
            raise
        except sqlite3.Error as exc:
            raise ScanError(f"Could not update the scan job database: {exc}") from exc
        finally:
            connection.close()


def doctor() -> None:
    scanimage = resolve_scanimage()
    try:
        version = subprocess.run(
            [str(scanimage), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ScanError(f"Could not run scanimage: {exc}") from exc
    if version.returncode:
        raise ScanError(version.stderr.strip() or "Could not read scanimage version.")
    print(version.stdout.strip())
    devices = list_scanners(scanimage)
    for device_id, description in devices:
        print(f"{device_id}: {description}")
    if not any("lide 400" in description.lower() for _, description in devices):
        raise ScanError(
            "The Canon LiDE 400 was not detected. Check the USB connection and "
            "run `sane-find-scanner -q`."
        )


def list_jobs(state_dir: Path, limit: int = 20) -> None:
    from .history_cli import list_jobs as show_jobs
    with database.use_state(state_dir):
        show_jobs(limit=limit)
