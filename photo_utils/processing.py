from __future__ import annotations

from . import database
from .naming import identity, day_directory, master_id, serialized_derivatives, existing_master

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple, cast
from importlib.metadata import version
from numpy.typing import NDArray

import cv2
import numpy as np
import tifffile

from .scanning import sha256_file


ALGORITHM_VERSION = "polaroid-sheet-v1"
MANIFEST_VERSION = 2
DETECTION_MAX_DIMENSION = 1800
DETECTION_THRESHOLD = 70
EXPECTED_CARDS = 4
OUTPUT_NAMES = tuple("print-{:02d}.tif".format(index) for index in range(1, 5))


class ProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class CardRegion:
    corners: Tuple[Tuple[float, float], ...]
    center: Tuple[float, float]
    bounds: Tuple[float, float, float, float]


@dataclass(frozen=True)
class CardPlan:
    region: CardRegion
    thick_side: str
    rotation_quarters: int
    width: int
    height: int
    border_confidence: float


def _read_source(source: Path) -> Tuple[NDArray[Any], dict[str, Any]]:
    if not source.is_file():
        raise ProcessingError("Source image does not exist or is not a file: {}".format(source))
    try:
        # This tifffile release lacks complete page/tag type annotations.
        with cast(Any, tifffile.TiffFile(source)) as image_file:
            if len(image_file.pages) != 1: raise ProcessingError("Scanner source must contain exactly one image page.")
            page = image_file.pages[0]
            image: NDArray[Any] = page.asarray()
            tags = page.tags
            metadata: dict[str, Any] = {}
            x_resolution = tags.get("XResolution")
            y_resolution = tags.get("YResolution")
            resolution_unit = tags.get("ResolutionUnit")
            if x_resolution and y_resolution and resolution_unit:
                unit = int(resolution_unit.value)
                if unit == 2:
                    metadata["resolution"] = (
                        float(x_resolution.value[0]) / float(x_resolution.value[1]),
                        float(y_resolution.value[0]) / float(y_resolution.value[1]),
                    )
                    metadata["resolution_unit"] = "INCH"
                elif unit == 3:
                    metadata["resolution"] = (
                        float(x_resolution.value[0]) / float(x_resolution.value[1]) * 2.54,
                        float(y_resolution.value[0]) / float(y_resolution.value[1]) * 2.54,
                    )
                    metadata["resolution_unit"] = "CENTIMETER"
            profile = tags.get("InterColorProfile") or tags.get("ICCProfile")
            if profile:
                metadata["icc_profile"] = profile.value
    except (OSError, tifffile.TiffFileError, ValueError) as exc:
        raise ProcessingError("Could not read TIFF source {}: {}".format(source, exc)) from exc

    if image.ndim == 2:
        image = np.repeat(image[:, :, np.newaxis], 3, axis=2)
    if (
        image.ndim != 3
        or image.shape[2] != 3
        or image.dtype not in (np.dtype("uint8"), np.dtype("uint16"))
    ):
        raise ProcessingError(
            "Expected an 8-bit or 16-bit RGB TIFF; found shape {} and dtype {}."
            .format(image.shape, image.dtype)
        )
    if min(image.shape[:2]) < 32:
        raise ProcessingError("Source image is too small to contain a scanner sheet.")
    return image, metadata


def _gray8(image: NDArray[Any]) -> NDArray[Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    if gray.dtype == np.uint16:
        return (gray / 257.0).astype(np.uint8)
    return gray


def _ordered_corners(points: NDArray[Any]) -> NDArray[Any]:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    sums = points.sum(axis=1)
    differences = points[:, 1] - points[:, 0]
    ordered = np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(differences)],
            points[np.argmax(sums)],
            points[np.argmax(differences)],
        ],
        dtype=np.float32,
    )
    if len({(round(float(x), 2), round(float(y), 2)) for x, y in ordered}) != 4:
        raise ProcessingError("Could not determine four distinct print corners.")
    return ordered


def detect_cards(image: NDArray[Any], kind: str = "polaroids") -> list[CardRegion]:
    height, width = image.shape[:2]
    scale = min(1.0, DETECTION_MAX_DIMENSION / float(max(height, width)))
    detection_width = max(1, int(round(width * scale)))
    detection_height = max(1, int(round(height * scale)))
    small = cv2.resize(
        _gray8(image),
        (detection_width, detection_height),
        interpolation=cv2.INTER_AREA,
    )
    if kind == 'prints':
        edges = np.concatenate((small[0,:],small[-1,:],small[:,0],small[:,-1]))
        background = float(np.median(edges))
        if float(np.percentile(np.abs(edges.astype(float)-background),90)) > 20:
            raise ProcessingError('Scanner background is not uniform; leave a clear margin around separated prints.')
        mask = (np.abs(small.astype(float)-background)>25).astype(np.uint8)*255
    else:
        mask = cv2.threshold(small, DETECTION_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
    )
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[CardRegion] = []
    frame_area = detection_width * detection_height
    for contour in contours:
        area = cv2.contourArea(contour)
        _x, _y, box_width, box_height = cv2.boundingRect(contour)
        if (
            area < frame_area * 0.015
            or box_width < detection_width * 0.10
            or box_height < detection_height * 0.08
        ):
            continue
        aspect = box_width / float(box_height)
        if not (0.25 if kind == "prints" else 0.5) <= aspect <= (4.0 if kind == "prints" else 2.0):
            continue

        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.015 * perimeter, True)
        rectangle = cv2.minAreaRect(contour)
        rectangular_area = rectangle[1][0]*rectangle[1][1]
        if kind == "prints" and (rectangular_area <= 0 or area/rectangular_area < .88 or area > frame_area*.85
                or _x <= 2 or _y <= 2 or _x+box_width >= detection_width-2 or _y+box_height >= detection_height-2):
            raise ProcessingError("Ambiguous or touching print boundary; separate prints against a contrasting background.")
        if len(polygon) == 4 and cv2.isContourConvex(polygon):
            points = polygon.reshape(4, 2).astype(np.float32)
        else:
            rectangle = cv2.minAreaRect(contour)
            rectangle_area = rectangle[1][0] * rectangle[1][1]
            if rectangle_area <= 0 or area / rectangle_area < 0.85:
                continue
            points = cv2.boxPoints(rectangle)
        points[:, 0] *= width / float(detection_width)
        points[:, 1] *= height / float(detection_height)
        ordered = _ordered_corners(points)
        mean = ordered.mean(axis=0)
        center = (float(mean[0]), float(mean[1]))
        bounds = (
            float(ordered[:, 0].min()),
            float(ordered[:, 1].min()),
            float(ordered[:, 0].max()),
            float(ordered[:, 1].max()),
        )
        candidates.append(
            CardRegion(
                corners=tuple((float(x), float(y)) for x, y in ordered),
                center=center,
                bounds=bounds,
            )
        )

    if kind == 'prints':
        if not 1 <= len(candidates) <= 20:
            raise ProcessingError('Expected 1–20 separated rectangular prints; detected '+str(len(candidates))+'. Use a contrasting background.')
        # Stable spatial order, grouping centers into rows using print height.
        candidates.sort(key=lambda card:(card.center[1],card.center[0]))
        rows: list[list[CardRegion]] = []
        for card in candidates:
            row = next((r for r in rows if abs(r[0].center[1]-card.center[1]) < .35*min(r[0].bounds[3]-r[0].bounds[1],card.bounds[3]-card.bounds[1])),None)
            if row is None: rows.append([card])
            else: row.append(card)
        return [card for row in rows for card in sorted(row,key=lambda c:c.center[0])]
    if len(candidates) != EXPECTED_CARDS:
        raise ProcessingError(
            "Expected exactly four separated print borders; detected {}. "
            "No outputs were written. Ensure the full sheet is in frame and "
            "the prints do not overlap.".format(len(candidates))
        )
    candidates.sort(key=lambda card: (card.center[1], card.center[0]))
    # Two spatial rows, then left-to-right within each row.
    candidates[:2] = sorted(candidates[:2], key=lambda card: card.center[0])
    candidates[2:] = sorted(candidates[2:], key=lambda card: card.center[0])
    return candidates


def _warp_card(image: NDArray[Any], region: CardRegion) -> NDArray[Any]:
    corners = np.asarray(region.corners, dtype=np.float32)
    top_left, top_right, bottom_right, bottom_left = corners
    width = int(
        round(
            max(
                np.linalg.norm(top_right - top_left),
                np.linalg.norm(bottom_right - bottom_left),
            )
        )
    ) + 1
    height = int(
        round(
            max(
                np.linalg.norm(bottom_left - top_left),
                np.linalg.norm(bottom_right - top_right),
            )
        )
    ) + 1
    if min(width, height) < 32:
        raise ProcessingError("Detected print is too small to rectify safely.")
    destination = np.array(
        [
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(
        image,
        transform,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _thickest_border(image: NDArray[Any]) -> Tuple[str, float]:
    thumbnail = cv2.resize(_gray8(image), (400, 320), interpolation=cv2.INTER_AREA)
    min_dimension = min(thumbnail.shape)
    near = max(1, int(round(min_dimension * 0.05)))
    far = max(near + 1, int(round(min_dimension * 0.25)))
    y1, y2 = int(thumbnail.shape[0] * 0.25), int(thumbnail.shape[0] * 0.75)
    x1, x2 = int(thumbnail.shape[1] * 0.25), int(thumbnail.shape[1] * 0.75)
    scores = {
        "top": float(thumbnail[near:far, x1:x2].mean()),
        "right": float(thumbnail[y1:y2, -far:-near].mean()),
        "bottom": float(thumbnail[-far:-near, x1:x2].mean()),
        "left": float(thumbnail[y1:y2, near:far].mean()),
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    confidence = ranked[0][1] - ranked[1][1]
    if ranked[0][1] < 90 or confidence < 25:
        raise ProcessingError(
            "The Polaroid's wide border is ambiguous (edge brightness scores: {}). "
            "No output was written for this print.".format(
                ", ".join("{}={:.0f}".format(side, score) for side, score in scores.items())
            )
        )
    return ranked[0][0], confidence


def plan_cards(image: NDArray[Any], kind: str = "polaroids") -> list[CardPlan]:
    plans: list[CardPlan] = []
    rotations_to_bottom = {"bottom": 0, "left": 1, "top": 2, "right": 3}
    for region in (detect_cards(image) if kind == "polaroids" else detect_cards(image,kind)):
        warped = _warp_card(image, region)
        if kind == 'prints':
            height,width=warped.shape[:2]
            plans.append(CardPlan(region,'not applicable',0,width,height,0.0))
            continue
        side, confidence = _thickest_border(warped)
        rotation = rotations_to_bottom[side]
        height, width = warped.shape[:2]
        if (rotation % 2) != 0:
            width, height = height, width
        if width >= height:
            raise ProcessingError(
                "A detected wide border would leave the print landscape after "
                "uprighting it. Refusing to guess its orientation."
            )
        plans.append(
            CardPlan(
                region=region,
                thick_side=side,
                rotation_quarters=rotation,
                width=width,
                height=height,
                border_confidence=confidence,
            )
        )
    return plans


def _output_resolution(metadata: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {"metadata": None}
    if "resolution" in metadata:
        options["resolution"] = metadata["resolution"]
        options["resolutionunit"] = metadata["resolution_unit"]
    if "icc_profile" in metadata:
        profile = metadata["icc_profile"]
        options["extratags"] = [
            (34675, "B", len(profile), profile, False),
        ]
    return options


def _provenance_metadata(metadata: dict[str, Any], kind: str = "polaroids") -> dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "parameters": {
            "detection_max_dimension": DETECTION_MAX_DIMENSION,
            "detection_threshold_8bit": DETECTION_THRESHOLD,
            "expected_cards": EXPECTED_CARDS if kind == "polaroids" else None,
            "interpolation": "cubic",
            "wide_border_alignment": "bottom" if kind == "polaroids" else None,
        },
        "backend_versions": {
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "tifffile": version("tifffile"),
        },
        "source_metadata": {
            "resolution": metadata.get("resolution"),
            "resolution_unit": metadata.get("resolution_unit"),
            "icc_profile_preserved": "icc_profile" in metadata,
        },
    }


def _atomic_write_manifest(path: Path, contents: dict[str, Any]) -> None:
    database.save_record(path, contents)


def _load_manifest(path: Path) -> dict[str, Any]:
    return database.read_record(path)


def _validate_existing_job(
    output_dir: Path,
    source: Path,
    source_sha256: str,
    plans: Sequence[CardPlan],
    names: Sequence[str] = OUTPUT_NAMES,
    manifest_name: str = "manifest.json",
    kind: str = "polaroids",
) -> Optional[dict[str, Any]]:
    manifest_path = output_dir / manifest_name
    if not output_dir.exists() or (manifest_name != "manifest.json" and not database.record_exists(manifest_path)):
        return None
    if not output_dir.is_dir() or not database.record_exists(manifest_path):
        raise ProcessingError(
            "Output path already exists and is not a Photo Utilities processing job: "
            "{}".format(output_dir)
        )
    manifest = _load_manifest(manifest_path)
    if (
        manifest.get("algorithm") != (ALGORITHM_VERSION if kind == "polaroids" else "ordinary-print-sheet-v1")
        or manifest.get("source_path") != str(source)
        or manifest.get("source_sha256") != source_sha256
    ):
        raise ProcessingError(
            "Output folder belongs to a different source or processing version: {}"
            .format(output_dir)
        )
    records: Any = manifest.get("cards")
    if (
        not isinstance(records, list)
        or len(cast(list[Any], records)) != len(plans)
        or any(
            not isinstance(card, dict)
            or cast(dict[str, Any], card).get("filename") != names[index]
            for index, card in enumerate(cast(list[Any], records))
        )
    ):
        raise ProcessingError("Existing processing manifest has an invalid card list.")
    if manifest.get("status") == "completed":
        for card in manifest["cards"]:
            output = output_dir / card["filename"]
            if not output.is_file() or sha256_file(output) != card.get("sha256"):
                raise ProcessingError(
                    "Completed derivative is missing or changed; refusing to overwrite: "
                    "{}".format(output)
                )
        return manifest
    if manifest.get("status") not in ("running", "failed", "interrupted"):
        raise ProcessingError("Existing processing job has an unknown state.")
    return manifest


def list_sheet_sources(root: Path, limit: int = 20) -> list[Path]:
    if not root.is_dir():
        return []
    sources: list[Path] = []
    try:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in (".tif", ".tiff"):
                continue
            if path.name.startswith(".") or ".partial" in path.name:
                continue
            parsed = identity(path)
            if parsed and parsed[3] != "master":
                continue
            if database.record_exists(path.parent / "manifest.json"):
                continue
            if any(part.endswith("-prints") for part in path.relative_to(root).parts[:-1]):
                continue
            sources.append(path)
    except OSError as exc:
        raise ProcessingError("Could not list scanner sheets under {}: {}".format(root, exc)) from exc
    try:
        sources.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    except OSError as exc:
        raise ProcessingError("Could not inspect scanner sheet dates: {}".format(exc)) from exc
    return sources[:limit]


@serialized_derivatives
def process_sheet(
    source_path: Path,
    *,
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
    state_dir: Optional[Path] = None,
    kind: str = "polaroids",
) -> list[Path]:
    source = source_path.expanduser().resolve()
    if not source.is_file():
        raise ProcessingError("Source image does not exist or is not a file: {}".format(source))
    try:
        source_digest = sha256_file(source)
    except OSError as exc:
        raise ProcessingError("Could not checksum source TIFF {}: {}".format(source, exc)) from exc
    image, metadata = _read_source(source)
    if kind not in ("polaroids","prints"): raise ProcessingError("Unknown sheet kind")
    cards = plan_cards(image) if kind == "polaroids" else plan_cards(image,kind)
    try:
        source_unchanged = sha256_file(source) == source_digest
    except OSError as exc:
        raise ProcessingError("Could not verify source TIFF after reading: {}".format(exc)) from exc
    if not source_unchanged:
        raise ProcessingError("Source TIFF changed while it was being read; no outputs were written.")
    parsed = identity(source)
    day = day_directory(source) if parsed else None
    legacy_destination = output_dir.expanduser().resolve() if output_dir else source.with_name(source.stem + "-prints")
    legacy_job = not parsed and database.record_exists(legacy_destination / "manifest.json")
    if not parsed and not legacy_job:
        parsed, day = existing_master(source, dry_run)
    readable_id = master_id(parsed[0], parsed[1]) if parsed else None
    names = tuple(f"{readable_id}-{index:02d}-print.tif" for index in range(1, len(cards)+1)) if parsed else tuple(f"print-{index:02d}.tif" for index in range(1,len(cards)+1))
    manifest_name = f"{readable_id}-prints.manifest.json" if parsed else "manifest.json"
    destination = (
        output_dir.expanduser().resolve()
        if output_dir is not None
        else (day / "prints" if day is not None else source.with_name(source.stem + "-prints"))
    )
    if destination == source or destination in source.parents:
        raise ProcessingError("Output directory must not contain the source TIFF.")
    print("Source: {}".format(source))
    print(
        "Detected {} {} prints; preserving {}-bit sample depth."
        .format(len(cards), kind, image.dtype.itemsize * 8)
    )
    print("Output folder: {}".format(destination))
    for index, plan in enumerate(cards, 1):
        print(
            "  {}: {} x {} px, wide border {} -> bottom"
            .format(names[index - 1], plan.width, plan.height, plan.thick_side)
        )
    source_digest = sha256_file(source)
    manifest_path = destination / manifest_name
    existing = _validate_existing_job(destination, source, source_digest, cards, names, manifest_name, kind)
    if dry_run:
        if existing and existing.get("status") == "completed":
            print("The matching output folder is already complete and checksum-verified.")
        elif existing:
            print("The matching interrupted job can resume in its existing output folder.")
        elif destination.exists():
            print("The output path is occupied; processing will refuse to overwrite it.")
        print("Dry run only; no output directory, images, or manifest were written.")
        return []

    if existing and existing.get("status") == "completed":
        existing.update(_provenance_metadata(metadata,kind))
        existing.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        _atomic_write_manifest(manifest_path, existing)
        print("This sheet is already processed; verified derivatives were left unchanged.")
        return [destination / name for name in names]
    if existing is None:
        try:
            destination.mkdir(parents=True, exist_ok=bool(parsed))
        except FileExistsError as exc:
            raise ProcessingError(
                "Output directory was created by another operation; refusing to use it: "
                "{}".format(destination)
            ) from exc
        except OSError as exc:
            raise ProcessingError("Could not create output directory {}: {}".format(destination, exc)) from exc
        manifest: dict[str, Any] = {
            "job_id": str(uuid.uuid4()),
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "algorithm": ALGORITHM_VERSION if kind == "polaroids" else "ordinary-print-sheet-v1",
            "sheet_kind":kind,
            **_provenance_metadata(metadata,kind),
            **({"scan_date": parsed[0], "master_id": readable_id, "parent_id": readable_id, "processing_stage": "print"} if parsed else {}),
            "output_location": str(destination),
            "source_path": str(source),
            "source_sha256": source_digest,
            "source_size_bytes": source.stat().st_size,
            "cards": [
                {
                    "filename": names[index],
                    "print_number": index + 1,
                    "parent_id": readable_id,
                    "bounds": list(plan.region.bounds),
                    "corners": [list(point) for point in plan.region.corners],
                    "wide_border": plan.thick_side,
                    "rotation_quarters_counter_clockwise": plan.rotation_quarters,
                    "border_confidence": plan.border_confidence,
                    "width": plan.width,
                    "height": plan.height,
                }
                for index, plan in enumerate(cards)
            ],
        }
    else:
        manifest = existing
        # Resume the stored spatial identities, even if detection ordering changes.
        ordered: list[CardPlan] = []
        for record in manifest["cards"]:
            matches = [plan for plan in cards if [list(point) for point in plan.region.corners] == record.get("corners")]
            if len(matches) != 1:
                raise ProcessingError("Detected geometry differs from assigned print identities; refusing to renumber.")
            ordered.append(matches[0])
        cards = ordered
        manifest["status"] = "running"
        manifest.pop("error", None)
    if kind == 'prints':
        manifest['parameters'].update(expected_cards=None, detection_threshold_8bit=None,
            segmentation='difference >25 from uniform border median; rectangularity >=.88',wide_border_alignment=None)
    _atomic_write_manifest(manifest_path, manifest)

    outputs: list[Path] = []
    try:
        for index, plan in enumerate(cards):
            record = manifest["cards"][index]
            destination_path = destination / names[index]
            if (
                destination_path.is_file()
                and record.get("sha256")
                and sha256_file(destination_path) == record["sha256"]
            ):
                outputs.append(destination_path)
                continue
            warped = _warp_card(image, plan.region)
            upright = np.rot90(warped, k=plan.rotation_quarters)
            temporary_path = destination / (names[index] + ".partial-" + uuid.uuid4().hex)
            try:
                tifffile.imwrite(
                    temporary_path,
                    upright,
                    photometric="rgb",
                    **_output_resolution(metadata)
                )
                record["sha256"] = sha256_file(temporary_path)
                record["dtype"] = str(upright.dtype)
                record["shape"] = list(upright.shape)
                _atomic_write_manifest(manifest_path, manifest)
                os.link(temporary_path, destination_path)
                temporary_path.unlink()
            except (OSError, tifffile.TiffFileError, ValueError) as exc:
                raise ProcessingError(
                    "Could not write derivative {}: {}".format(destination_path, exc)
                ) from exc
            record["sha256"] = sha256_file(destination_path)
            record["dtype"] = str(upright.dtype)
            record["shape"] = list(upright.shape)
            outputs.append(destination_path)
            _atomic_write_manifest(manifest_path, manifest)
        if sha256_file(source) != source_digest:
            raise ProcessingError("Source TIFF changed during processing; outputs are marked failed.")
        manifest["status"] = "completed"
        _atomic_write_manifest(manifest_path, manifest)
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        manifest["error"] = "Interrupted by user."
        _atomic_write_manifest(manifest_path, manifest)
        raise
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        _atomic_write_manifest(manifest_path, manifest)
        if isinstance(exc, ProcessingError):
            raise
        raise ProcessingError("Sheet processing failed: {}".format(exc)) from exc

    print("Completed: {} derivatives saved with a resumable manifest.".format(len(outputs)))
    return outputs
