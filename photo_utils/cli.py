import argparse
import sys
import shlex
from pathlib import Path
from typing import Any, Optional, Sequence, cast

from . import database, history_cli
from .processing import (
    ProcessingError,
    list_sheet_sources,
    process_sheet,
)
from .naming import identity
from .retouch import RetouchError, RetouchOptions, retouch
from .similarity import SimilarityError, find_similar
from .scanning import (
    MODES,
    RESOLUTIONS,
    ScanError,
    default_root,
    default_scan_folder,
    default_state_dir,
    doctor,
    run_scan,
    validate_folder_name,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="photo-utils")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("doctor", help="Check scanimage and scanner availability")

    scan = commands.add_parser(
        "scan",
        help="Acquire, split, and conservatively retouch a LiDE 400 scanner sheet",
    )
    scan.add_argument(
        "--folder",
        default=default_scan_folder(),
        help="Deprecated compatibility option; scans always use their initiation date",
    )
    scan.add_argument(
        "--root",
        type=Path,
        default=default_root(),
        help=f"Parent folder for scans (default: {default_root()})",
    )
    scan.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir(),
        help=f"Local job database directory (default: {default_state_dir()})",
    )
    scan.add_argument("--device", help="SANE device ID; otherwise detect LiDE 400")
    scan.add_argument(
        "--resolution",
        type=int,
        choices=RESOLUTIONS,
        default=600,
        help="Scan DPI (default: 600; only 600 has been hardware-tested)",
    )
    scan.add_argument(
        "--mode",
        choices=tuple(MODES),
        default="48-bit-color",
        help="Scan mode (default: 48-bit-color)",
    )
    scan.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate scanner settings and print the plan without acquiring",
    )
    scan.add_argument(
        "--retouch",
        choices=("polaroid", "none"),
        default="polaroid",
        help="Process as a Polaroid (default) or leave the scanned sheet unsplit",
    )
    scan.add_argument("--kind", choices=("polaroids", "prints"), default="polaroids",
                      help="Sheet type; ordinary print splitting is not implemented yet")
    scan.add_argument("--find-similar", action="store_true", help="Group saved prints before retouching; write a local HTML report")

    process = commands.add_parser(
        "process-sheet",
        help="Split a Polaroid scanner TIFF, then apply the polaroid retouch profile",
    )
    process.add_argument("source", type=Path, help="Scanner-sheet TIFF to process")
    process.add_argument(
        "--output-dir",
        type=Path,
        help="Output folder (default: original scan date/prints for identified masters)",
    )
    process.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect prints and show the plan without writing outputs",
    )
    process.add_argument(
        "--retouch",
        choices=("polaroid", "none"),
        default="polaroid",
        help="Retouch extracted prints using the polaroid profile (default: polaroid)",
    )
    process.add_argument("--kind", choices=("polaroids", "prints"), default="polaroids",
                         help="Sheet type; ordinary print splitting is not implemented yet")
    process.add_argument("--find-similar", action="store_true", help="Group saved prints before retouching; write a local HTML report")

    similar = commands.add_parser("similar", help="Find related photo groups with local Vision + SIFT")
    similar.add_argument("targets", nargs="+", type=Path, help="Image files or folders; folders do not recurse by default")
    similar.add_argument("--recursive", action="store_true", help="Include images in subfolders")
    similar.add_argument("--report", type=Path, help="New HTML file; default: similarity.html beside the images, versioned on reruns")
    similar.add_argument("--vision-threshold", type=float, default=.45, help="Vision candidate distance cutoff (default: .45)")
    similar.add_argument("--dry-run", action="store_true", help="List the plan without decoding or writing anything")
    similar.add_argument("--no-db", action="store_true", help="Create only the HTML report without SQLite persistence")

    retouch_command = commands.add_parser(
        "retouch",
        help="Apply the Polaroid ImageMagick recipe to one TIFF or a folder of TIFFs",
    )
    retouch_command.add_argument("target", type=Path, help="TIFF file or folder (folders recurse)")
    retouch_command.add_argument("--profile", choices=("polaroid",), default="polaroid")
    retouch_command.add_argument("--output-dir", type=Path, help="Separate output folder")
    retouch_command.add_argument("--version-history", action="store_true", help="Keep a new numbered retouch version (v02 onward)")
    retouch_command.add_argument("--preview", action="store_true", help="Write labeled before/after JPEG previews")
    retouch_command.add_argument("--dry-run", action="store_true", help="Report the recipe without writing outputs")

    jobs = commands.add_parser("jobs", help="List scan, split, and retouch jobs")
    jobs.add_argument("--limit", type=int, default=20)
    jobs.add_argument("--date", type=history_cli.date_argument)
    jobs.add_argument("--type", choices=("scan","split","retouch","similarity"))
    jobs.add_argument("--status", choices=("pending","running","completed","partial","failed"))
    assets = commands.add_parser("assets", help="Browse assets and parent relationships")
    assets.add_argument("--date", type=history_cli.date_argument)
    assets.add_argument("--stage", choices=("master","print","retouch","external"))
    assets.add_argument("--status")
    job = commands.add_parser("job", help="Inspect or explicitly export a job")
    job_actions = job.add_subparsers(dest="action",required=True)
    job_show = job_actions.add_parser("show")
    job_show.add_argument("job_id")
    job_export = job_actions.add_parser("export")
    job_export.add_argument("job_id")
    job_export.add_argument("--format", choices=("json",),default="json")
    job_export.add_argument("--output", type=Path, help="Export file; defaults to stdout")
    recipe = commands.add_parser("recipe", help="Inspect complete processing parameters")
    recipe_actions = recipe.add_subparsers(dest="action",required=True)
    recipe_show = recipe_actions.add_parser("show")
    recipe_show.add_argument("asset_id")
    recipe_show.add_argument("--recipe-id", help="Select one history entry")
    history = commands.add_parser("history", help="Inspect chronological asset history and lineage")
    history.add_argument("asset_id")
    db = commands.add_parser("db", help="Database diagnostics")
    db_actions = db.add_subparsers(dest="action",required=True)
    db_check = db_actions.add_parser("check")
    db_check.add_argument("--checksums", action="store_true",help="Also verify image SHA-256 checksums")
    for command in (process,similar,retouch_command,jobs,assets,job_show,job_export,recipe_show,history,db_check):
        command.add_argument("--state-dir",type=Path,help="Local SQLite job database directory (default: configured state directory)")
    return parser


def prompt_choice(prompt: str, choices: str, *, default: Optional[str] = None) -> str:
    allowed = {choice.lower() for choice in choices}
    formatted_choices = choices
    if default:
        formatted_choices = "".join(
            choice.upper() if choice.lower() == default.lower() else choice.lower()
            for choice in choices
        )
    suffix = f" [{'/'.join(formatted_choices)}]"
    while True:
        answer = input(f"{prompt}{suffix}: ").strip().lower()
        if not answer and default:
            return default.lower()
        if answer in allowed:
            return answer
        print(f"Please enter one of: {', '.join(choices)}.")


def prompt_scan_folder(root: Path) -> str:
    default_folder = default_scan_folder()
    default_target = root.expanduser() / default_folder
    use_default = prompt_choice(
        f"Use default scan target ({default_target})?",
        "YN",
        default="Y",
    )
    if use_default == "y":
        return default_folder

    while True:
        folder = input("Scan folder name (one folder name, not a path): ").strip()
        try:
            return validate_folder_name(folder)
        except ScanError as exc:
            print(exc)


def prompt_sheet_source(root: Path) -> Path:
    sources = list_sheet_sources(root)
    if not sources:
        raise ProcessingError(
            "No scanner TIFF sheets were found under {}. Scan a sheet first, "
            "or use `photo-utils process-sheet <path-to-tiff>`.".format(root)
        )
    print("\nRecent scanner sheets")
    for index, source in enumerate(sources, 1):
        try:
            label = source.relative_to(root)
        except ValueError:
            label = source
        print("  {}) {}".format(index, label))
    while True:
        answer = input("Select a sheet number [1]: ").strip()
        if not answer:
            return sources[0]
        try:
            selected = int(answer)
        except ValueError:
            selected = 0
        if 1 <= selected <= len(sources):
            return sources[selected - 1]
        print("Please enter a number from 1 to {}.".format(len(sources)))


def process_and_retouch(
    source: Path,
    *,
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
    profile: str = "polaroid",
    find_similar_groups: bool = False,
) -> None:
    outputs = process_sheet(source, output_dir=output_dir, dry_run=dry_run)
    if find_similar_groups:
        if dry_run:
            print("After splitting: find similar groups in the saved prints, before retouching.")
        elif outputs:
            find_similar([outputs[0].parent])
    if not outputs or profile == "none":
        return
    if identity(outputs[0]):
        for output in outputs:
            retouch(output, options=RetouchOptions(profile=profile))
    else:
        retouch(outputs[0].parent, options=RetouchOptions(profile=profile))


def run_interactive_menu() -> int:
    print("\nPhoto Utilities")
    print("  D) Doctor - check scanner availability")
    print("  S) Scan   - acquire and optionally process a sheet")
    print("  R) Retouch a TIFF or folder")
    print("  G) Find related photo groups")
    print("  H) History & Database")
    print("  Q) Quit")
    choice = prompt_choice("Select an action", "DSRGHQ")
    if choice == "q":
        return 0
    if choice == "d":
        doctor()
        return 0

    if choice == "h":
        history_cli.menu()
        return 0
    if choice == "g":
        target = Path(input("Image folder: ").strip()).expanduser()
        recursive = prompt_choice("Include subfolders?", "YN", default="N") == "y"
        dry_run = prompt_choice("Dry run?", "YN", default="N") == "y"
        find_similar([target], recursive=recursive, dry_run=dry_run)
        return 0
    if choice == "r":
        target = Path(input("TIFF or folder: ").strip()).expanduser()
        dry_run = prompt_choice("Dry run?", "YN",default="N") == "y"
        retouch(target,dry_run=dry_run)
        return 0

    print("\nScan")
    print("  S) Scan a new sheet")
    print("  P) Process an existing Polaroid sheet (then retouch the prints)")
    print("  T) Ordinary print page (not implemented yet)")
    print("  Q) Quit")
    scan_choice = prompt_choice("Select an action", "SPTQ", default="S")
    if scan_choice == "q":
        return 0
    if scan_choice == "t":
        raise ProcessingError("Print Splitting Not Implemented Yet")

    root = default_root()
    if scan_choice == "p":
        source = prompt_sheet_source(root)
        dry_run = (
            prompt_choice(
                "Dry run (detect prints without writing files)?",
                "YN",
                default="N",
            )
            == "y"
        )
        process_and_retouch(source, dry_run=dry_run)
        return 0

    polaroid = prompt_choice(
        "Are these scans Polaroids? (No keeps the sheet unsplit for later processing)",
        "YN",
        default="Y",
    ) == "y"
    folder = default_scan_folder()
    print(f"Scan target: {root / folder / 'masters'}")
    dry_run = (
        prompt_choice(
            "Dry run (validate settings without scanning)?",
            "YN",
            default="N",
        )
        == "y"
    )
    output_path = run_scan(
        folder=folder,
        root=root,
        state_dir=default_state_dir(),
        dry_run=dry_run,
    )
    if not dry_run and output_path is not None and polaroid:
        process_and_retouch(output_path, profile="polaroid")
    return 0


def configuration_value(value: Any) -> Any:
    """Convert argparse paths, including multi-target lists, for job provenance."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [configuration_value(item) for item in cast(Sequence[Any], value)]
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    state_token = database.STATE.set(getattr(args,"state_dir",None))
    command_token = database.CLI_COMMAND.set("photo-utils " + shlex.join(list(argv) if argv is not None else sys.argv[1:]))
    config_token = database.CLI_CONFIG.set({name:configuration_value(value) for name,value in vars(args).items()})
    try:
        if args.command is None:
            if not sys.stdin.isatty():
                print(
                    "photo-utils: interactive menu requires a terminal; use "
                    "`photo-utils doctor`, `photo-utils scan`, "
                    "`photo-utils process-sheet`, `photo-utils retouch`, or "
                    "`photo-utils jobs`.",
                    file=sys.stderr,
                )
                return 2
            return run_interactive_menu()
        if args.command == "doctor":
            doctor()
        elif args.command == "scan":
            if args.kind == "prints":
                raise ProcessingError("Print Splitting Not Implemented Yet")
            if args.find_similar and args.retouch == "none":
                raise ProcessingError("--find-similar requires a split sheet; scan --retouch none keeps the sheet unsplit.")
            output_path = run_scan(
                folder=args.folder,
                root=args.root,
                state_dir=args.state_dir,
                resolution=args.resolution,
                mode=args.mode,
                requested_device=args.device,
                dry_run=args.dry_run,
            )
            if output_path is not None and args.retouch == "polaroid":
                if args.find_similar:
                    process_and_retouch(output_path, profile=args.retouch, find_similar_groups=True)
                else:
                    process_and_retouch(output_path, profile=args.retouch)
            elif args.dry_run and args.find_similar:
                print("After scanning: split/rotate/save, find related groups, then apply the Polaroid recipe.")
        elif args.command == "process-sheet":
            if args.kind == "prints":
                raise ProcessingError("Print Splitting Not Implemented Yet")
            process_and_retouch(
                args.source,
                output_dir=args.output_dir,
                dry_run=args.dry_run,
                profile=args.retouch,
                **({"find_similar_groups": True} if args.find_similar else {}),
            )
        elif args.command == "similar":
            find_similar(args.targets, recursive=args.recursive, report=args.report,
                         dry_run=args.dry_run, no_db=args.no_db, threshold=args.vision_threshold,
                         state_dir=args.state_dir)
        elif args.command == "retouch":
            retouch(
                args.target,
                output_dir=args.output_dir,
                options=RetouchOptions(
                    profile=args.profile,
                ),
                dry_run=args.dry_run,
                preview=args.preview,
                version_history=args.version_history,
            )
        elif args.command in {"jobs","job","assets","recipe","history","db"}:
            return history_cli.dispatch(args)
    except (ScanError, ProcessingError, RetouchError, SimilarityError, database.DatabaseError, OSError) as exc:
        print(f"photo-utils: error: {exc}", file=sys.stderr)
        return 1
    except EOFError:
        print("\nInput ended; no operation started.")
        return 0
    except KeyboardInterrupt:
        print(
            "Operation interrupted. Partial data, if any, was retained.",
            file=sys.stderr,
        )
        return 130
    finally:
        database.STATE.reset(state_token)
        database.CLI_COMMAND.reset(command_token)
        database.CLI_CONFIG.reset(config_token)
    return 0
