---
name: photo-toolkit
description: Run the local PhotoUtilities toolkit from plain-English requests to scan Polaroid pages, process existing sheets, or find related groups in camera photos and lab scans. Creates local review reports and preserves original photographs.
---

# Photo toolkit

Use the existing local `photo-utils` CLI. Locate the repository from the current
workspace or `~/Documents/PhotoScans/PhotoUtilities`; read its `AGENTS.md` and
the relevant README commands. Run `.venv/bin/photo-utils` from that repository.
Do not recreate analysis in ad hoc scripts.

Route the request:

- **Find related photos:** `similar "/path/to/image-folder"`. JPEG, HEIC/HEIF,
  PNG and single-image TIFF are supported. Analyze originals before manual
  editing when available. Folders are shallow by default; use `--recursive`
  only when subfolders are part of the intended batch. Multiple files/folders
  are accepted; use `--report "/existing/folder/new-report.html"` when inputs
  span multiple folders. Ask for a target only when it cannot be inferred.
- **Scan a Polaroid page:** `scan --kind polaroids --find-similar`. This saves
  the master, separates/rectifies four bordered Polaroids, aligns their wide
  borders, saves original prints, groups that day's saved prints, then applies
  the default Polaroid recipe. The scan/print/retouch layout is retained.
- **Process an existing Polaroid sheet:** `process-sheet "/path/to/master.tif"
  --kind polaroids --find-similar`. Add `--retouch none` when splitting and
  grouping without edits is requested.
- **Scan/split ordinary prints:** `scan --kind prints` or `process-sheet
  "/path/to/sheet.tif" --kind prints` deliberately errors with
  `Print Splitting Not Implemented Yet` before scanning or writing files.
  Explain this limit; do not silently process ordinary prints as Polaroids.

Similarity uses the accepted Vision distance <.45 OR strict SIFT rule. Do not
raise cutoffs, introduce hashes, or declare identity/accuracy from scores alone.
The single local HTML report contains embedded previews, likely/potential
groups and unmatched photos at the bottom. Groups allow chaining. Link the
saved report and summarize group sizes, groups larger than three and unmatched
counts. Do not send private previews to a cloud model for visual review.

Routine similarity results and source-asset links are saved in existing SQLite;
derivative history can show inherited source analysis without rematching edited
versions. Use `--no-db` for report-only analysis, and `--dry-run` for a no-write
plan. Default report reruns create numbered versions; explicit `--report`
paths refuse collisions. Images are never moved or edited by `similar`.

Native Vision requires macOS 14+ and Apple Command Line Tools; the bundled
Swift helper builds locally on first use. Native Vision may need execution
outside an agent sandbox. Treat decoding/helper failures as failed analysis,
not unmatched images. Report the actual failure and stop dependent processing;
never silently omit failed inputs. A scan request authorizes acquisition;
physical validation of the latest wrapper remains a separate check.
