from __future__ import annotations

from . import database
from .naming import identity, day_directory, tracking, serialized_derivatives

import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple, cast

import numpy as np
from numpy.typing import NDArray
import tifffile

from .scanning import sha256_file


RETOUCH_ALGORITHM = "polaroid-magick-srgb-v2"
RETOUCH_OUTPUT_ALGORITHMS = {
    RETOUCH_ALGORITHM,
    "polaroid-magick-v1",
    "faithful-polaroid-v1",
    "faithful-polaroid-v2",
}
RECIPE_VERSION = 4
SRGB_PROFILE_PATH = Path("/System/Library/ColorSync/Profiles/sRGB Profile.icc")
POLAROID_MAGICK_ARGUMENTS = (
    "-sigmoidal-contrast",
    "4x35%",
    "-gamma",
    "1.70",
    "-level",
    "5%,98.5%",
    "-gamma",
    "1.09",
    "-channel",
    "R",
    "-gamma",
    "1.04",
    "+channel",
    "-depth",
    "16",
)
SUPPORTED_SUFFIXES = {".tif", ".tiff"}
UInt16Image = NDArray[np.uint16]
FloatArray = NDArray[np.float64]
EXIFTOOL_METADATA_ARGS = (
    "-all:all",
    "--ImageWidth",
    "--ImageHeight",
    "--BitsPerSample",
    "--SamplesPerPixel",
    "--PhotometricInterpretation",
    "--Compression",
    "--PlanarConfiguration",
    "--RowsPerStrip",
    "--StripOffsets",
    "--StripByteCounts",
    "--TileWidth",
    "--TileLength",
    "--TileOffsets",
    "--TileByteCounts",
)


class RetouchError(RuntimeError):
    pass


@dataclass(frozen=True)
class PhotoArea:
    bounds: Tuple[int, int, int, int]
    confidence: float
    measurements: dict[str, float]


@dataclass(frozen=True)
class RetouchOptions:
    profile: str = "polaroid"


@dataclass(frozen=True)
class RetouchPlan:
    area: Optional[PhotoArea]
    metrics: dict[str, Any]
    decisions: dict[str, str]
    warnings: Tuple[str, ...]


def _resolve_executable(environment_name: str, candidates: Sequence[str]) -> Path:
    configured = os.environ.get(environment_name)
    if configured:
        executable = Path(configured).expanduser()
        if executable.is_file() and os.access(executable, os.X_OK):
            return executable.resolve()
        raise RetouchError(
            "{} is not an executable file: {}".format(environment_name, executable)
        )
    located = shutil.which("magick" if environment_name.endswith("MAGICK") else "exiftool")
    if located:
        return Path(located).resolve()
    for candidate in candidates:
        executable = Path(candidate)
        if executable.is_file() and os.access(executable, os.X_OK):
            return executable.resolve()
    tool = "ImageMagick 7 (`magick`)" if environment_name.endswith("MAGICK") else "ExifTool"
    raise RetouchError(
        "Cannot find {}. Add it to PATH or set {} to its executable path."
        .format(tool, environment_name)
    )


def resolve_magick() -> Path:
    return _resolve_executable(
        "PHOTO_UTILITIES_MAGICK",
        ("/opt/homebrew/bin/magick", "/usr/local/bin/magick"),
    )


def resolve_exiftool() -> Path:
    return _resolve_executable(
        "PHOTO_UTILITIES_EXIFTOOL",
        ("/opt/homebrew/bin/exiftool", "/usr/local/bin/exiftool"),
    )


def resolve_srgb_profile() -> Path:
    profile = SRGB_PROFILE_PATH
    if not profile.is_file():
        raise RetouchError(
            "The system sRGB ICC profile was not found at {}.".format(profile)
        )
    return profile.resolve()


def _run_command(command: Sequence[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RetouchError("Could not run {}: {}".format(label, exc)) from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or (
            "exit status {}".format(result.returncode)
        )
        raise RetouchError("{} failed: {}".format(label, detail))
    return result


def _check_tools() -> dict[str, str]:
    magick = resolve_magick()
    exiftool = resolve_exiftool()
    magick_version = _run_command([str(magick), "-version"], "ImageMagick version check")
    first_line = magick_version.stdout.splitlines()[0] if magick_version.stdout else ""
    if "ImageMagick 7" not in first_line or not re.search(r"\bQ16(?:-HDRI)?\b", first_line):
        raise RetouchError(
            "Retouch requires ImageMagick 7 with Q16 or Q16-HDRI support; found {!r}."
            .format(first_line)
        )
    exiftool_version = _run_command([str(exiftool), "-ver"], "ExifTool version check")
    return {
        "imagemagick": first_line,
        "exiftool": exiftool_version.stdout.strip(),
    }


def _source_metadata(source: Path) -> tuple[UInt16Image, dict[str, Any]]:
    if not source.is_file():
        raise RetouchError("Input TIFF does not exist or is not a file: {}".format(source))
    try:
        with cast(Any, tifffile.TiffFile(source)) as tif:
            if len(tif.pages) == 0:
                raise RetouchError("TIFF contains no image pages: {}".format(source))
            page: Any = tif.pages[0]
            if page.samplesperpixel != 3 or page.photometric != tifffile.PHOTOMETRIC.RGB:
                raise RetouchError(
                    "Expected a three-channel RGB TIFF; found photometric {} and {} samples."
                    .format(page.photometric, page.samplesperpixel)
                )
            if page.dtype != np.dtype("uint16"):
                raise RetouchError(
                    "Faithful retouch accepts 16-bit/channel TIFF only; found {}."
                    .format(page.dtype)
                )
            if len(tif.pages) != 1:
                raise RetouchError("Multi-page TIFF input is not supported.")
            pixels: UInt16Image = page.asarray()
            tags: Any = page.tags
            metadata: dict[str, Any] = {}
            for tag_name in (
                "XResolution",
                "YResolution",
                "ResolutionUnit",
            ):
                tag: Any = tags.get(tag_name)
                if tag is None:
                    continue
                value: Any = tag.value
                if tag_name in ("XResolution", "YResolution"):
                    value = (
                        float(cast(Any, value[0]))
                        / float(cast(Any, value[1]))
                        if isinstance(value, tuple)
                        else float(value)
                    )
                elif tag_name == "ResolutionUnit":
                    value = int(value)
                metadata[tag_name] = value
            profile: Any = tags.get("InterColorProfile")
            if profile is not None:
                try:
                    metadata["ICCProfile"] = bytes(profile.value)
                except (TypeError, ValueError) as exc:
                    raise RetouchError(
                        "TIFF contains an unreadable embedded ICC profile: {}"
                        .format(source)
                    ) from exc
    except RetouchError:
        raise
    except (OSError, tifffile.TiffFileError, ValueError) as exc:
        raise RetouchError("Could not read TIFF {}: {}".format(source, exc)) from exc
    if pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 64:
        raise RetouchError(
            "Expected a sufficiently large 16-bit RGB image; found shape {}."
            .format(pixels.shape)
        )
    return pixels, metadata


def _smoothed(profile: FloatArray) -> FloatArray:
    width = max(9, int(round(len(profile) * 0.007)))
    if width % 2 == 0:
        width += 1
    kernel = np.ones(width, dtype=np.float64) / width
    padded = np.pad(profile, (width // 2, width // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _edge_crossing(
    profile: FloatArray, threshold: float, from_start: bool
) -> Optional[int]:
    below = _smoothed(profile) < threshold
    run = max(5, int(round(len(profile) * 0.004)))
    if from_start:
        candidates = np.convolve(
            below.astype(np.int32),
            np.ones(run, dtype=np.int32),
            mode="valid",
        )
        found = np.flatnonzero(candidates == run)
        return int(found[0]) if len(found) else None
    reversed_candidates = np.convolve(
        below[::-1].astype(np.int32),
        np.ones(run, dtype=np.int32),
        mode="valid",
    )
    found = np.flatnonzero(reversed_candidates == run)
    return len(profile) - int(found[0]) - run if len(found) else None


def detect_photo_area(image: UInt16Image) -> Optional[PhotoArea]:
    height, width = image.shape[:2]
    values: FloatArray = image.astype(np.float64) / 65535.0
    gray: FloatArray = values.mean(axis=2)
    y_profile: FloatArray = gray[:, int(width * 0.20) : int(width * 0.80)].mean(axis=1)
    x_profile: FloatArray = gray[int(height * 0.15) : int(height * 0.70), :].mean(axis=0)

    y_edge: FloatArray = np.concatenate(
        (
            y_profile[: max(1, int(height * 0.05))],
            y_profile[int(height * 0.80) :],
        )
    )
    y_inner: FloatArray = y_profile[int(height * 0.20) : int(height * 0.65)]
    x_edge: FloatArray = np.concatenate(
        (
            x_profile[: max(1, int(width * 0.06))],
            x_profile[int(width * 0.94) :],
        )
    )
    x_inner: FloatArray = x_profile[int(width * 0.20) : int(width * 0.80)]
    y_border, y_center = float(np.median(y_edge)), float(np.median(y_inner))
    x_border, x_center = float(np.median(x_edge)), float(np.median(x_inner))
    y_start = _edge_crossing(y_profile, y_center * 0.70 + y_border * 0.30, True)
    y_end = _edge_crossing(y_profile, y_center * 0.70 + y_border * 0.30, False)
    x_start = _edge_crossing(x_profile, x_center * 0.70 + x_border * 0.30, True)
    x_end = _edge_crossing(x_profile, x_center * 0.70 + x_border * 0.30, False)
    if None in (x_start, y_start, x_end, y_end):
        return None
    assert x_start is not None and y_start is not None
    assert x_end is not None and y_end is not None

    x0 = int(round(x_start * width / float(len(x_profile))))
    x1 = int(round(x_end * width / float(len(x_profile))))
    y0 = int(round(y_start * height / float(len(y_profile))))
    y1 = int(round(y_end * height / float(len(y_profile))))
    inset_x = max(2, int(round(width * 0.01)))
    inset_y = max(2, int(round(height * 0.01)))
    x0 += inset_x
    x1 -= inset_x
    y0 += inset_y
    y1 -= inset_y
    if x1 <= x0 or y1 <= y0:
        return None
    x_fraction = (x0 / float(width), x1 / float(width))
    y_fraction = (y0 / float(height), y1 / float(height))
    area_ratio = ((x1 - x0) * (y1 - y0)) / float(width * height)
    photo_aspect = (x1 - x0) / float(y1 - y0)
    contrast = min(y_border - y_center, x_border - x_center)
    if (
        contrast < 0.12
        or x_fraction[0] < 0.03
        or x_fraction[0] > 0.20
        or x_fraction[1] < 0.80
        or x_fraction[1] > 0.97
        or y_fraction[0] < 0.03
        or y_fraction[0] > 0.25
        or y_fraction[1] < 0.60
        or y_fraction[1] > 0.86
        or not 0.50 <= photo_aspect <= 1.40
        or area_ratio < 0.35
    ):
        return None
    confidence = min(1.0, max(0.0, contrast / 0.35))
    return PhotoArea(
        bounds=(x0, y0, x1, y1),
        confidence=confidence,
        measurements={
            "border_relative_brightness_x": x_border,
            "photo_relative_brightness_x": x_center,
            "border_relative_brightness_y": y_border,
            "photo_relative_brightness_y": y_center,
            "border_photo_contrast": contrast,
            "photo_area_fraction": area_ratio,
            "conservative_inset_x_px": float(inset_x),
            "conservative_inset_y_px": float(inset_y),
        },
    )


def _validate_options(options: RetouchOptions) -> None:
    if options.profile != "polaroid":
        raise RetouchError("Only the 'polaroid' retouch profile is supported.")


def plan_retouch(image: UInt16Image, options: RetouchOptions) -> RetouchPlan:
    _validate_options(options)
    area = detect_photo_area(image)
    metrics = {
        "image_width": int(image.shape[1]),
        "image_height": int(image.shape[0]),
        "photo_area_detected_for_reference_only": area is not None,
        "photo_area_bounds_xyxy": list(area.bounds) if area is not None else None,
        "adjustment_region": "entire TIFF, including Polaroid border",
    }
    return RetouchPlan(
        area=area,
        metrics=metrics,
        decisions={
            "ImageMagick": "fixed Polaroid recipe applied to the full TIFF"
        },
        warnings=(),
    )


def polaroid_magick_command(
    magick: Path, source: Path, output: Path, srgb_profile: Path
) -> list[str]:
    return [
        str(magick),
        str(source),
        *POLAROID_MAGICK_ARGUMENTS[:-2],
        "-profile",
        str(srgb_profile),
        *POLAROID_MAGICK_ARGUMENTS[-2:],
        "tiff:{}".format(output),
    ]


def _render_polaroid(
    magick: Path, source: Path, output: Path, srgb_profile: Path
) -> None:
    _run_command(
        polaroid_magick_command(magick, source, output, srgb_profile),
        "ImageMagick Polaroid retouch",
    )
    if not output.is_file():
        raise RetouchError("ImageMagick did not create the Polaroid TIFF derivative.")


def _icc_profile(path: Path) -> Optional[bytes]:
    try:
        with cast(Any, tifffile.TiffFile(path)) as tif:
            profile: Any = tif.pages[0].tags.get("InterColorProfile")
            if profile is None:
                return None
            try:
                return bytes(profile.value)
            except (TypeError, ValueError) as exc:
                raise RetouchError(
                    "TIFF contains an unreadable embedded ICC profile: {}"
                    .format(path)
                ) from exc
    except (OSError, tifffile.TiffFileError) as exc:
        raise RetouchError("Could not inspect ICC profile in {}: {}".format(path, exc)) from exc


def _write_tiff(path: Path, image: UInt16Image, metadata: dict[str, Any]) -> None:
    options: dict[str, Any] = {"photometric": "rgb", "metadata": None}
    x_resolution = metadata.get("XResolution")
    y_resolution = metadata.get("YResolution")
    resolution_unit = metadata.get("ResolutionUnit")
    if x_resolution and y_resolution and resolution_unit in (2, 3):
        options["resolution"] = (x_resolution, y_resolution)
        options["resolutionunit"] = "INCH" if resolution_unit == 2 else "CENTIMETER"
    profile = metadata.get("ICCProfile")
    if profile:
        options["extratags"] = [
            (34675, "B", len(profile), profile, False),
        ]
    try:
        tifffile.imwrite(path, image, **options)
    except (OSError, tifffile.TiffFileError, ValueError) as exc:
        raise RetouchError("Could not write TIFF derivative {}: {}".format(path, exc)) from exc


def _copy_metadata(exiftool: Path, source: Path, output: Path) -> None:
    command = [
        str(exiftool),
        "-TagsFromFile",
        str(source),
        *EXIFTOOL_METADATA_ARGS,
        "--ICC_Profile",
        "-overwrite_original",
        str(output),
    ]
    _run_command(command, "ExifTool metadata copy")


def _verify_output(output: Path, expected_icc_profile: bytes) -> None:
    try:
        with cast(Any, tifffile.TiffFile(output)) as tif:
            page: Any = tif.pages[0]
            if (
                len(tif.pages) != 1
                or page.dtype != np.dtype("uint16")
                or page.samplesperpixel != 3
                or page.photometric != tifffile.PHOTOMETRIC.RGB
            ):
                raise RetouchError(
                    "Rendered derivative is not a single-page 16-bit/channel RGB TIFF: {}"
                    .format(output)
                )
    except (OSError, tifffile.TiffFileError) as exc:
        raise RetouchError("Could not verify TIFF derivative {}: {}".format(output, exc)) from exc
    output_profile = _icc_profile(output)
    if output_profile != expected_icc_profile:
        raise RetouchError("Output does not contain the requested sRGB ICC profile.")


def _atomic_json(path: Path, contents: dict[str, Any]) -> None:
    database.save_record(path, contents)


def _publish_no_replace(temporary: Path, destination: Path) -> None:
    try:
        os.link(str(temporary), str(destination))
        temporary.unlink()
    except FileExistsError as exc:
        raise RetouchError(
            "Refusing to overwrite an existing retouch output: {}".format(destination)
        ) from exc
    except OSError as exc:
        raise RetouchError(
            "Could not publish retouch output {} without overwriting: {}"
            .format(destination, exc)
        ) from exc


def _metadata_summary(exiftool: Path, path: Path) -> dict[str, Any]:
    tags = [
        "ImageDescription",
        "DateTimeOriginal",
        "CreateDate",
        "ModifyDate",
        "Artist",
        "Copyright",
        "Make",
        "Model",
        "Software",
        "XResolution",
        "YResolution",
        "ResolutionUnit",
        "ICC_Profile:ProfileDescription",
    ]
    result = _run_command(
        [str(exiftool), "-j", "-s", *("-{}".format(tag) for tag in tags), str(path)],
        "ExifTool metadata inspection",
    )
    try:
        value = json.loads(result.stdout)
        return value[0] if value and isinstance(value[0], dict) else {}
    except (ValueError, IndexError) as exc:
        raise RetouchError("ExifTool returned invalid JSON metadata for {}.".format(path)) from exc


def _write_preview(
    magick: Path,
    source: Path,
    output: Path,
    preview: Path,
) -> None:
    font = next(
        (
            candidate
            for candidate in (
                Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                Path("/System/Library/Fonts/Supplemental/Verdana.ttf"),
                Path("/Library/Fonts/Arial.ttf"),
                Path("/opt/homebrew/share/fonts/dejavu/DejaVuSans.ttf"),
            )
            if candidate.is_file()
        ),
        None,
    )
    if font is None:
        configured = os.environ.get("PHOTO_UTILITIES_PREVIEW_FONT")
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.is_file():
                font = candidate
        if font is None:
            raise RetouchError(
                "Could not find a font for the labeled preview. Install a system "
                "font or set PHOTO_UTILITIES_PREVIEW_FONT to a font file."
            )
    temporary = preview.with_name(
        "{}.partial-{}.jpg".format(preview.stem, uuid.uuid4().hex[:8])
    )
    if preview.exists():
        raise RetouchError("Refusing to overwrite an existing preview: {}".format(preview))
    command = [
        str(magick),
        str(source),
        "-resize",
        "500x500>",
        "-background",
        "white",
        "-gravity",
        "south",
        "-splice",
        "0x32",
        "-fill",
        "black",
        "-font",
        str(font),
        "-pointsize",
        "16",
        "-annotate",
        "+0+6",
        "BEFORE",
        "(",
        str(output),
        "-resize",
        "500x500>",
        "-background",
        "white",
        "-gravity",
        "south",
        "-splice",
        "0x32",
        "-fill",
        "black",
        "-font",
        str(font),
        "-pointsize",
        "16",
        "-annotate",
        "+0+6",
        "AFTER",
        ")",
        "+append",
        "-quality",
        "90",
        "jpeg:{}".format(temporary),
    ]
    try:
        _run_command(command, "ImageMagick before/after preview")
        if not temporary.is_file():
            raise RetouchError("ImageMagick did not create the before/after preview.")
        _publish_no_replace(temporary, preview)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _build_recipe(
    source: Path,
    output: Path,
    source_digest: str,
    output_digest: str,
    plan: RetouchPlan,
    options: RetouchOptions,
    tool_versions: dict[str, str],
    source_metadata: dict[str, Any],
    output_metadata: dict[str, Any],
    source_has_icc: bool,
    preview: bool,
    srgb_profile: Path,
) -> dict[str, Any]:
    warnings: list[str] = list(plan.warnings)
    if not source_has_icc:
        warnings.append(
            "Input has no embedded ICC profile; the system sRGB profile was assigned "
            "to the derivative for viewing."
        )
    missing = sorted(set(source_metadata) - set(output_metadata))
    if missing:
        warnings.append("Some queried metadata fields were not present after rendering: " + ", ".join(missing))
    return {
        **tracking(source, "retouch"),
        "recipe_version": RECIPE_VERSION,
        "algorithm": RETOUCH_ALGORITHM,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source),
        "source_sha256": source_digest,
        "output_path": str(output),
        "output_sha256": output_digest,
        "profile": options.profile,
        "profile_options": _options_dict(options),
        "preview_path": (
            str(output.with_suffix(output.suffix + ".before-after.jpg"))
            if preview
            else None
        ),
        "input_bits_per_channel": 16,
        "output_bits_per_channel": 16,
        "icc_profile": "converted to sRGB" if source_has_icc else "sRGB assigned",
        "analysis": plan.metrics,
        "decisions": plan.decisions,
        "actual_parameters": {
            "imagemagick_arguments": [
                *POLAROID_MAGICK_ARGUMENTS[:-2],
                "-profile",
                str(srgb_profile),
                *POLAROID_MAGICK_ARGUMENTS[-2:],
            ],
            "output_icc_profile": "sRGB",
            "output_icc_profile_path": str(srgb_profile),
            "output_icc_profile_sha256": sha256_file(srgb_profile),
            "adjustment_region": "entire TIFF, including Polaroid border",
            "sharpen": False,
            "denoise": False,
            "restore": False,
            "pixel_operation": "ImageMagick 7 on full 16-bit RGB TIFF",
        },
        "metadata_fields_missing_after_render": missing,
        "tool_versions": tool_versions,
        "warnings": warnings,
    }


def _print_plan(
    source: Path,
    output: Path,
    plan: RetouchPlan,
    metadata: dict[str, Any],
    srgb_profile: Path,
) -> None:
    print("Input:  {}".format(source))
    print("Output: {}".format(output))
    print("Photo area: {}".format(plan.metrics.get("photo_area_bounds_xyxy", "uncertain")))
    print("ICC profile: {}".format("embedded" if "ICCProfile" in metadata else "untagged"))
    for name, decision in plan.decisions.items():
        print("  {}: {}".format(name.replace("_", " ").title(), decision))
    arguments = (
        *POLAROID_MAGICK_ARGUMENTS[:-2],
        "-profile",
        str(srgb_profile),
        *POLAROID_MAGICK_ARGUMENTS[-2:],
    )
    print("  ImageMagick arguments: {}".format(" ".join(arguments)))
    for warning in plan.warnings:
        print("  Warning: {}".format(warning))
    if "ICCProfile" not in metadata:
        print("  Warning: input is untagged; the output will be tagged sRGB.")


def _single_retouch(
    source: Path,
    output: Path,
    options: RetouchOptions,
    *,
    dry_run: bool,
    preview: bool,
    srgb_profile: Path,
    srgb_profile_bytes: bytes,
    tools: Optional[dict[str, str]] = None,
    job_id: Optional[str] = None,
) -> dict[str, Any]:
    image, metadata = _source_metadata(source)
    plan = plan_retouch(image, options)
    print("Profile: {}".format(options.profile))
    _print_plan(source, output, plan, metadata, srgb_profile)
    if dry_run:
        print("  Output ICC profile: {}".format(srgb_profile))
        print("Dry run only; no derivative, recipe, or preview was written.")
        return {"source": str(source), "output": str(output), "dry_run": True}
    tool_versions = tools or _check_tools()
    source_digest = sha256_file(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        recipe_path = output.with_suffix(output.suffix + ".recipe.json")
        try:
            recipe = database.read_record(recipe_path)
        except (OSError, ValueError, database.DatabaseError) as exc:
            raise RetouchError(
                "Retouch output already exists without a readable recipe; refusing "
                "to overwrite it: {}".format(output)
            ) from exc
        if (
            recipe.get("algorithm") != RETOUCH_ALGORITHM
            or recipe.get("source_path") != str(source)
            or recipe.get("source_sha256") != source_digest
            or recipe.get("output_sha256") != sha256_file(output)
            or recipe.get("profile_options") != _options_dict(options)
            or recipe.get("preview_path")
            != (
                str(output.with_suffix(output.suffix + ".before-after.jpg"))
                if preview
                else None
            )
        ):
            raise RetouchError(
                "Existing retouch output does not match this source or settings; "
                "refusing to overwrite it: {}".format(output)
            )
        _verify_output(output, srgb_profile_bytes)
        preview_path = output.with_suffix(output.suffix + ".before-after.jpg")
        if preview and not preview_path.exists():
            _write_preview(resolve_magick(), source, output, preview_path)
        return recipe
    temporary = output.with_name(
        "{}.partial-{}.tif".format(output.stem, uuid.uuid4().hex[:8])
    )
    try:
        _render_polaroid(resolve_magick(), source, temporary, srgb_profile)
        _copy_metadata(resolve_exiftool(), source, temporary)
        if sha256_file(source) != source_digest:
            raise RetouchError("Source TIFF changed during retouch; output will not be published.")
        _verify_output(temporary, srgb_profile_bytes)
        exiftool = resolve_exiftool()
        recipe = _build_recipe(source,output,source_digest,sha256_file(temporary),plan,options,
                               tool_versions,_metadata_summary(exiftool,source),
                               _metadata_summary(exiftool,temporary),"ICCProfile" in metadata,preview,srgb_profile)
        if job_id is not None:
            recipe["job_id"] = job_id
        recipe_path = output.with_suffix(output.suffix + ".recipe.json")
        _atomic_json(recipe_path,recipe)
        _publish_no_replace(temporary, output)
        _atomic_json(recipe_path,recipe)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    if preview:
        _write_preview(
            resolve_magick(),
            source,
            output,
            output.with_suffix(output.suffix + ".before-after.jpg"),
        )
    return recipe


def _list_tiffs(target: Path) -> tuple[list[Path], bool]:
    resolved = target.expanduser().resolve()
    if resolved.is_file():
        parsed = identity(resolved)
        if parsed and parsed[3] == "retouch":
            raise RetouchError("Retouch the original print instead of chaining edits.")
        if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise RetouchError(
                "Retouch currently accepts only 16-bit RGB TIFF files: {}".format(resolved)
            )
        return [resolved], True
    if not resolved.is_dir():
        raise RetouchError("Input path does not exist or is not a file/folder: {}".format(resolved))
    if resolved.name == "retouches":
        raise RetouchError("Retouch the original prints instead of chaining edits.")
    root_manifest_path = resolved / "manifest.json"
    if database.record_exists(root_manifest_path):
        try:
            root_manifest_value: Any = database.read_record(root_manifest_path)
        except (OSError, ValueError):
            root_manifest_value = {}
        root_manifest: dict[str, Any] = (
            cast(dict[str, Any], root_manifest_value)
            if isinstance(root_manifest_value, dict)
            else {}
        )
        if root_manifest.get("algorithm") in RETOUCH_OUTPUT_ALGORITHMS:
            raise RetouchError(
                "This folder already contains retouched derivatives. Retouch the "
                "original TIFFs instead of chaining edits."
            )
    sources: list[Path] = []
    try:
        for path in resolved.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if (
                path.name.startswith(".")
                or ".partial-" in path.name
                or ".partial." in path.name
            ):
                continue
            parsed = identity(path)
            if parsed and parsed[3] != "print":
                continue
            if any(part.endswith("-retouched") for part in path.relative_to(resolved).parts[:-1]):
                continue
            belongs_to_retouch_output = False
            for ancestor in path.parents:
                manifest_path = ancestor / "manifest.json"
                if not database.record_exists(manifest_path):
                    continue
                try:
                    manifest_value: Any = database.read_record(manifest_path)
                except (OSError, ValueError):
                    manifest_value = {}
                manifest: dict[str, Any] = (
                    cast(dict[str, Any], manifest_value)
                    if isinstance(manifest_value, dict)
                    else {}
                )
                if manifest.get("algorithm") in RETOUCH_OUTPUT_ALGORITHMS:
                    belongs_to_retouch_output = True
                    break
            if belongs_to_retouch_output:
                continue
            sources.append(path.resolve())
    except OSError as exc:
        raise RetouchError("Could not list TIFF files in {}: {}".format(resolved, exc)) from exc
    sources.sort(key=lambda path: str(path).casefold())
    if not sources:
        raise RetouchError("No TIFF images found under {}.".format(resolved))
    return sources, False


def _manifest_matches(
    manifest_path: Path,
    source_root: Path,
    output_root: Path,
    source_digests: dict[str, str],
    options: RetouchOptions,
    preview: bool,
) -> Optional[dict[str, Any]]:
    if not output_root.exists() or (manifest_path.name != "manifest.json" and not database.record_exists(manifest_path)):
        return None
    if not output_root.is_dir() or not database.record_exists(manifest_path):
        raise RetouchError(
            "Retouch output path exists and is not a recognized job folder: {}"
            .format(output_root)
        )
    try:
        manifest_value: Any = database.read_record(manifest_path)
    except (OSError, ValueError) as exc:
        raise RetouchError("Could not read existing retouch manifest: {}".format(exc)) from exc
    if not isinstance(manifest_value, dict):
        raise RetouchError("Existing retouch manifest must contain a JSON object.")
    manifest: dict[str, Any] = cast(dict[str, Any], manifest_value)
    items_value = manifest.get("files")
    if not isinstance(items_value, list):
        raise RetouchError("Existing retouch manifest has an invalid files list.")
    file_records: list[dict[str, Any]] = []
    for item_value in cast(list[Any], items_value):
        if not isinstance(item_value, dict):
            raise RetouchError("Existing retouch manifest contains an invalid file record.")
        file_records.append(cast(dict[str, Any], item_value))
    manifest["files"] = file_records
    if (
        manifest.get("algorithm") != RETOUCH_ALGORITHM
        or manifest.get("source_root") != str(source_root)
        or manifest.get("profile") != options.profile
        or manifest.get("source_sha256") != source_digests
        or manifest.get("options") != _options_dict(options)
        or manifest.get("preview") != preview
    ):
        raise RetouchError(
            "Retouch output folder belongs to another source or settings. "
            "Choose a new --output-dir to retain both versions."
        )
    if manifest.get("status") == "completed":
        for item in file_records:
            if not isinstance(item.get("relative_output"), str):
                raise RetouchError("Existing retouch manifest contains an invalid file record.")
            relative_output = Path(item["relative_output"])
            if relative_output.is_absolute() or ".." in relative_output.parts:
                raise RetouchError("Existing retouch manifest contains an unsafe output path.")
            output = output_root / relative_output
            if not output.is_file() or sha256_file(output) != item.get("output_sha256"):
                raise RetouchError(
                    "Completed retouch output is missing or changed; refusing to replace: {}"
                    .format(output)
                )
            recipe = output.with_suffix(output.suffix + ".recipe.json")
            if not database.record_exists(recipe):
                raise RetouchError(
                    "Completed retouch recipe is missing; refusing to replace: {}"
                    .format(recipe)
                )
            if preview:
                preview_path = output.with_suffix(output.suffix + ".before-after.jpg")
                if not preview_path.is_file():
                    raise RetouchError(
                        "Completed retouch preview is missing; choose a new output "
                        "folder to regenerate it: {}".format(preview_path)
                    )
        return manifest
    if manifest.get("status") not in ("running", "failed", "interrupted"):
        raise RetouchError("Existing retouch job has an unknown state.")
    return manifest


def _options_dict(options: RetouchOptions) -> dict[str, Any]:
    profile = resolve_srgb_profile()
    return {
        "profile": options.profile,
        "imagemagick_arguments": list(POLAROID_MAGICK_ARGUMENTS),
        "output_icc_profile": str(profile),
        "output_icc_profile_sha256": sha256_file(profile),
        "adjustment_region": "entire TIFF, including Polaroid border",
    }


@serialized_derivatives
def retouch(
    target_path: Path,
    *,
    output_dir: Optional[Path] = None,
    options: Optional[RetouchOptions] = None,
    dry_run: bool = False,
    preview: bool = False,
    version_history: bool = False,
    state_dir: Optional[Path] = None,
) -> list[Path]:
    options = options or RetouchOptions()
    _validate_options(options)
    sources, single_file = _list_tiffs(target_path)
    target = target_path.expanduser().resolve()
    source_root = target.parent if single_file else target
    canonical = all(identity(source) and identity(source)[3] == "print" for source in sources)
    if canonical:
        days = {day_directory(source) for source in sources}
        if len(days) != 1:
            raise RetouchError("Process one scan date at a time.")
    destination = (
        output_dir.expanduser().resolve()
        if output_dir is not None
        else (day_directory(sources[0]) / "retouches" if canonical else source_root.with_name(source_root.name + "-retouched"))
    )
    if destination == source_root or destination in source_root.parents:
        raise RetouchError("Retouch output folder must not contain the source folder.")
    if not dry_run:
        tools = _check_tools()
    else:
        resolve_magick()
        resolve_exiftool()
        tools = {}
    srgb_profile = resolve_srgb_profile()
    try:
        srgb_profile_bytes = srgb_profile.read_bytes()
    except OSError as exc:
        raise RetouchError(
            "Could not read system sRGB ICC profile {}: {}".format(srgb_profile, exc)
        ) from exc
    digests = {str(path): sha256_file(path) for path in sources}
    # One operation/job can contain several retouched prints.
    if canonical:
        plans = []
        for source in sources:
            base = source.stem.removesuffix("-print") + "-retouch"
            output = destination / (base + ".tif")
            if version_history:
                version = 2
                while (destination / f"{base}-v{version:02d}.tif").exists():
                    version += 1
                output = destination / f"{base}-v{version:02d}.tif"
            plans.append((source, output))
        operation_key = uuid.uuid5(uuid.NAMESPACE_URL, database.encode({
            "outputs": [str(output) for _,output in plans], "sources":digests,
            "options":_options_dict(options), "preview":preview})).hex
        record_path = destination / (".retouch-" + operation_key)
        manifest = database.read_record(record_path, missing_ok=True) or {
            "job_id":str(uuid.uuid4()), "algorithm":RETOUCH_ALGORITHM,
            "created_at":datetime.now(timezone.utc).isoformat(),
            "scan_date":identity(sources[0])[0], "source_root":str(source_root),
            "source_sha256":digests, "options":_options_dict(options),
            "preview":preview, "files":[]}
        manifest.update(status="running")
        manifest.pop("error",None)
        if not dry_run:
            _atomic_json(record_path,manifest)
        results = []
        try:
            for source,output in plans:
                recipe = _single_retouch(source,output,options,dry_run=dry_run,preview=preview,
                                        srgb_profile=srgb_profile,srgb_profile_bytes=srgb_profile_bytes,
                                        tools=tools,job_id=manifest["job_id"])
                if not dry_run:
                    item = {"source_path":str(source),"source_sha256":digests[str(source)],
                            "relative_output":str(output.relative_to(destination)),
                            "output_sha256":recipe["output_sha256"]}
                    manifest["files"] = [record for record in manifest["files"] if record["relative_output"]!=item["relative_output"]]+[item]
                    _atomic_json(record_path,manifest)
                    results.append(output)
            if not dry_run:
                manifest.update(status="completed")
                _atomic_json(record_path,manifest)
        except BaseException as exc:
            if not dry_run:
                manifest.update(status="interrupted" if isinstance(exc,KeyboardInterrupt) or results else "failed",error=str(exc))
                _atomic_json(record_path,manifest)
            raise
        return results
    if version_history:
        raise RetouchError("--version-history requires identified extracted prints.")
    manifest_path = destination / "manifest.json"
    existing = _manifest_matches(
        manifest_path, source_root, destination, digests, options, preview
    )
    print("Input TIFFs: {}".format(len(sources)))
    print("Output folder: {}".format(destination))
    print("Output ICC profile: {}".format(srgb_profile))
    plans: list[tuple[Path, Path]] = []
    for source in sources:
        relative = Path(source.name) if single_file else source.relative_to(source_root)
        output = destination / relative
        image, metadata = _source_metadata(source)
        plan = plan_retouch(image, options)
        plans.append((source, output))
        _print_plan(source, output, plan, metadata, srgb_profile)
    if dry_run:
        print("Dry run only; no derivative, recipe, manifest, or preview was written.")
        return []
    if existing and existing.get("status") == "completed":
        _atomic_json(manifest_path,existing)
        print("Matching completed retouch job is checksum-verified; outputs were left unchanged.")
        return [destination / (Path(source.name) if single_file else source.relative_to(source_root)) for source in sources]
    if destination.exists() and existing is None:
        raise RetouchError("Retouch output folder already exists; refusing to overwrite it.")
    if existing is None:
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise RetouchError("Could not create retouch output folder: {}".format(exc)) from exc
        manifest: dict[str, Any] = {
            "manifest_version": 1,
            "algorithm": RETOUCH_ALGORITHM,
            "job_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_root": str(source_root),
            "source_sha256": digests,
            "profile": options.profile,
            "options": _options_dict(options),
            "preview": preview,
            "status": "running",
            "files": [],
        }
    else:
        manifest = existing
        manifest["status"] = "running"
        manifest.pop("error", None)
    _atomic_json(manifest_path, manifest)
    result_paths: list[Path] = []
    try:
        file_records: list[dict[str, Any]] = manifest["files"]
        for source, output in plans:
            relative = output.relative_to(destination)
            record = next(
                (
                    item
                    for item in file_records
                    if item.get("relative_output") == str(relative)
                ),
                None,
            )
            if (
                record
                and output.is_file()
                and sha256_file(output) == record.get("output_sha256")
            ):
                result_paths.append(output)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            recipe = _single_retouch(
                source,
                output,
                options,
                dry_run=False,
                preview=preview,
                srgb_profile=srgb_profile,
                srgb_profile_bytes=srgb_profile_bytes,
                tools=tools,
                job_id=manifest["job_id"],
            )
            item: dict[str, Any] = {
                "source_path": str(source),
                "source_sha256": cast(str, recipe["source_sha256"]),
                "relative_output": str(relative),
                "output_sha256": cast(str, recipe["output_sha256"]),
                "recipe_path": str(relative) + ".recipe.json",
            }
            if record:
                file_records[file_records.index(record)] = item
            else:
                file_records.append(item)
            result_paths.append(output)
            _atomic_json(manifest_path, manifest)
        if any(
            sha256_file(Path(path)) != digest
            for path, digest in digests.items()
        ):
            raise RetouchError("One or more source TIFFs changed during retouch.")
        manifest["status"] = "completed"
        _atomic_json(manifest_path, manifest)
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        manifest["error"] = "Interrupted by user."
        _atomic_json(manifest_path, manifest)
        raise
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        _atomic_json(manifest_path, manifest)
        if isinstance(exc, RetouchError):
            raise
        raise RetouchError("Retouch failed: {}".format(exc)) from exc
    print("Completed retouch for {} TIFF(s).".format(len(result_paths)))
    return result_paths
