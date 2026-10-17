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
from .batch import process_batch
from .review_server import serve_review
from .review_archive import restore_archive, compact_archive
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
        default=None,
        help="Optional auto-edit: Polaroids default to polaroid; ordinary prints default to none",
    )
    scan.add_argument("--kind", choices=("polaroids", "prints"), default="polaroids",
                      help="Sheet type: four bordered Polaroids or separated ordinary prints")
    scan.add_argument("--capture-only",action="store_true",help="Save the untouched sheet without splitting or review")
    scan.add_argument("--find-similar", action="store_true", help="Group saved prints before retouching; write a local HTML report")

    process = commands.add_parser(
        "process-sheet",
        help="Split a scanner sheet, auto-rotate prints and generate three-tier review before optional Polaroid edits",
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
        default=None,
        help="Optional auto-edit: Polaroids default to polaroid; ordinary prints default to none",
    )
    process.add_argument("--kind", choices=("polaroids", "prints"), default="polaroids",
                         help="Sheet type: four bordered Polaroids or separated ordinary prints")
    process.add_argument("--find-similar", action="store_true", help="Group saved prints before retouching; write a local HTML report")

    scan.add_argument("--no-focus-review", dest="focus_review", action="store_false", help="Skip experimental grouping/focus review")
    process.add_argument("--no-focus-review", dest="focus_review", action="store_false", help="Skip experimental grouping/focus review")

    batch = commands.add_parser("process", help="Process image folders: visual quarter-turns, grouping and three-tier review before optional Polaroid edits")
    batch.add_argument("targets", nargs="+", type=Path)
    batch.add_argument("--recursive", action="store_true")
    batch.add_argument("--report", type=Path)
    batch.add_argument("--retouch", choices=("none","polaroid"), default="none", help="Existing Polaroid TIFF recipe only; default: analysis without edits")
    batch.add_argument("--dry-run", action="store_true")
    batch.add_argument("--no-db", action="store_true")
    review = commands.add_parser("review", help="Open a local interactive review session for a completed focus job")
    review.add_argument("job_id")
    review.add_argument("--archive-root", type=Path, help="Default: PhotoScans/Blurry; must share sources filesystem")
    restore = commands.add_parser("restore-archive", help="Restore files moved by a review-archive job; keep verified ZIP")
    restore.add_argument("job_id")
    compact = commands.add_parser("compact-archive", help="Verify an existing review archive and retain only its ZIP in a dated folder")
    compact.add_argument("job_id")

    similar = commands.add_parser("similar", help="Find related photo groups with local Vision + SIFT")
    similar.add_argument("targets", nargs="+", type=Path, help="Image files or folders; folders do not recurse by default")
    similar.add_argument("--tier-review",action="store_true",help="Generate three-tier selection review")
    similar.add_argument("--focus-review", action="store_true", help="Include experimental focus suggestions and relative group highlights")
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

    jobs = commands.add_parser("jobs", help="List scan, split, retouch, similarity and review-archive jobs")
    jobs.add_argument("--limit", type=int, default=20)
    jobs.add_argument("--date", type=history_cli.date_argument)
    jobs.add_argument("--type", choices=("scan","split","retouch","similarity","review-archive"))
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
    for command in (batch,review,restore,compact,process,similar,retouch_command,jobs,assets,job_show,job_export,recipe_show,history,db_check):
        command.add_argument("--state-dir",type=Path,help="Local SQLite job database directory (default: configured state directory)")
    for command in (scan,process,batch):
        command.add_argument('--no-tier-review',dest='tier_review',action='store_false',help='Use the older focus-only report')
        command.add_argument('--no-auto-rotate',dest='auto_rotate',action='store_false',help='Use embedded orientation only')
        command.add_argument('--open-review',action='store_true',help='Open a local interactive review session after processing')
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
    focus_review: bool = False,
    tier_review: bool = True,
    auto_rotate: bool = True,
    kind: str = 'polaroids',
) -> Optional[Path]:
    if kind == 'prints' and profile != 'none': raise ProcessingError('Auto-edit is implemented only for Polaroids; use --retouch none.')
    outputs = process_sheet(source, output_dir=output_dir, dry_run=dry_run, kind=kind)
    review_report: Optional[Path] = None
    oriented_sources: dict[str,Path] = {}
    if find_similar_groups or focus_review:
        if dry_run:
            print("After splitting: auto-rotate quarter-turns, group saved prints and generate three-tier review before optional retouching." if focus_review and tier_review else "After splitting: group saved prints and flag focus for review before retouching." if focus_review else "After splitting: find similar groups in the saved prints, before retouching.")
        elif outputs:
            review_report = find_similar(outputs, focus=True, tiers=tier_review, auto_rotate=auto_rotate, oriented_sources=oriented_sources) if focus_review else find_similar([outputs[0].parent])
    if not outputs or profile == "none":
        return review_report
    if identity(outputs[0]) or oriented_sources:
        for output in outputs:
            retouch(oriented_sources.get(str(output),output), options=RetouchOptions(profile=profile))
    else:
        retouch(outputs[0].parent, options=RetouchOptions(profile=profile))
    return review_report


def open_report_review(report: Optional[Path]) -> None:
    if report is None: return
    with database.transaction() as db:
        row = db.execute("SELECT job_id FROM scan_jobs WHERE output_path=? AND processing_status='completed' ORDER BY started_at DESC LIMIT 1",(str(report),)).fetchone()
    if row is None: raise SimilarityError('No completed review job found for this report.')
    serve_review(row['job_id'])


def run_interactive_menu() -> int:
    while True:
        print("\nPhoto Utilities\n  S) Scan a sheet\n  P) Process a photo folder\n  E) Process an existing sheet\n  V) Review a previous run\n  U) Restore culled photos\n  M) Maintenance and other tools\n  Q) Quit")
        choice=prompt_choice('Select an action','SPEVUMQ')
        if choice=='q': return 0
        if choice=='v':
            serve_review(input('Review job ID: ').strip()); continue
        if choice=='u':
            restore_archive(input('Archive job ID: ').strip()); continue
        if choice=='m':
            print('D) Scanner diagnostics · H) History & database · G) Similar groups only · R) Retouch TIFFs · B) Back')
            action=prompt_choice('Maintenance','DHGRB')
            if action=='d': doctor()
            elif action=='h': history_cli.menu()
            elif action=='g': find_similar([Path(input('Image folder: ').strip()).expanduser()])
            elif action=='r': retouch(Path(input('TIFF or folder: ').strip()).expanduser())
            continue
        if choice=='p':
            target=Path(input('Photo folder: ').strip()).expanduser()
            recursive=prompt_choice('Include subfolders?','YN',default='Y')=='y'
            edit=prompt_choice('Are these Polaroid TIFFs to auto-edit?','YN',default='N')=='y'
            dry=prompt_choice('Dry run?','YN',default='N')=='y'
            report=process_batch([target],recursive=recursive,profile='polaroid' if edit else 'none',dry_run=dry)
        else:
            kind='polaroids' if prompt_choice('Sheet contains Polaroids (P) or ordinary prints (O)?','PO',default='P')=='p' else 'prints'
            profile='polaroid' if kind=='polaroids' and prompt_choice('Auto-edit the Polaroids?','YN',default='Y')=='y' else 'none'
            dry=prompt_choice('Dry run?','YN',default='N')=='y'
            source=prompt_sheet_source(default_root()) if choice=='e' else run_scan(folder=default_scan_folder(),root=default_root(),state_dir=default_state_dir(),dry_run=dry)
            report=process_and_retouch(source,profile=profile,kind=kind,focus_review=True,dry_run=dry) if source else None
        if report and prompt_choice('Open interactive review with cull/restore archive controls?','YN',default='Y')=='y':
            open_report_review(report)


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
            profile=args.retouch or ('polaroid' if args.kind=='polaroids' else 'none')
            if args.kind=='prints' and profile!='none': raise ProcessingError('Auto-edit is implemented only for Polaroids.')
            if args.capture_only and args.find_similar: raise ProcessingError('--capture-only cannot generate a print review.')
            output_path = run_scan(
                folder=args.folder,
                root=args.root,
                state_dir=args.state_dir,
                resolution=args.resolution,
                mode=args.mode,
                requested_device=args.device,
                dry_run=args.dry_run,
            )
            report=None
            if output_path is not None and not args.capture_only:
                report=process_and_retouch(output_path,profile=profile,kind=args.kind,
                    find_similar_groups=args.find_similar,focus_review=args.focus_review,
                    tier_review=args.tier_review,auto_rotate=args.auto_rotate)
            elif args.dry_run and not args.capture_only:
                print('After scanning: split/rectify prints, auto-rotate quarter-turns, generate three-tier review, then optional Polaroid edits.')
            if args.open_review: open_report_review(report)
        elif args.command == "process-sheet":
            profile=args.retouch or ('polaroid' if args.kind=='polaroids' else 'none')
            report=process_and_retouch(args.source,output_dir=args.output_dir,dry_run=args.dry_run,
                profile=profile,kind=args.kind,find_similar_groups=args.find_similar,
                focus_review=args.focus_review,tier_review=args.tier_review,auto_rotate=args.auto_rotate)
            if args.open_review: open_report_review(report)
        elif args.command == "similar":
            find_similar(args.targets, recursive=args.recursive, report=args.report,
                         dry_run=args.dry_run, no_db=args.no_db, threshold=args.vision_threshold,
                         state_dir=args.state_dir, focus=args.focus_review, tiers=args.tier_review)
        elif args.command == "process":
            report=process_batch(args.targets, recursive=args.recursive, report=args.report,
                          profile=args.retouch, dry_run=args.dry_run, no_db=args.no_db,
                          tiers=args.tier_review,auto_rotate=args.auto_rotate)
            if args.open_review and not args.no_db: open_report_review(report)
        elif args.command == "review":
            serve_review(args.job_id, archive_root=args.archive_root)
        elif args.command == "restore-archive":
            restore_archive(args.job_id)
        elif args.command == "compact-archive":
            result=compact_archive(args.job_id)
            print("ZIP-only archive:",result["archive"])
            if result["cleanup_errors"]:
                raise SimilarityError("Some duplicate copies were retained: "+"; ".join(result["cleanup_errors"]))
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
