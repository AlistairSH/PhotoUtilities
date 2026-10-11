# Standalone Czkawka comparison

Read-only experimental comparison with the user-accepted Vision <0.45 OR SIFT
candidate union. Independent from the production CLI, scanning, retouching and
SQLite. No source photographs or reports belong in Git.

The official Czkawka 12.0.2 Apple Silicon CLI was downloaded to the scan root's
`VisionExperiments/tools/czkawka-12.0.2/`, outside the repository. Its SHA-256
matched GitHub's published release digest:
`3362df5776b209b6365482768bc960e5a853f1b554787954c4a4c64e90bc2c75`.
No Homebrew GUI/dependency installation was needed.

Run from the repository root, with explicit local paths:

```sh
.venv/bin/python experiments/czkawka_compare/benchmark.py \
  /local/path/hash-sift-comparison --binary /local/path/czkawka_cli \
  --output /local/path/new-czkawka-report-folder
.venv/bin/python experiments/czkawka_compare/report.py \
  /local/path/new-czkawka-report-folder
.venv/bin/python -B -m unittest discover -s experiments/czkawka_compare -q
```

The runner refuses an existing output directory and checks that scanned JPGs
exactly match each saved baseline. Every image checksum is verified before and
after. No files are copied/moved/renamed. CLI flags explicitly include deletion
`NONE`, dry-run, cache disabled, minimum size 1 byte, no size/resolution exclusions,
and JPG-only enumeration. Rotation/mirroring invariance is off. The orchestrated
run also protected the production jobs.sqlite3 checksum and denied network
access via a process sandbox. No SQLite connection is opened.

The portable binary exited abnormally inside the agent sandbox but worked in
approved ordinary execution, including with network denied. It successfully
found a synthetic identical pair. The CLI's JSON is a list of image groups,
not all pairwise hash distances. Released source merges overlapping groups
transitively, and exported hashes are cleared; do not attach each entry's
`difference` value to every pair in a group. We compare **co-group membership**
with the combo's direct candidate pairs and label that distinction in galleries.

Twelve configurations cover the default Gradient/16/Nearest/difference-5 and
selected Gradient/Mean/Median variants, hash sizes 8/16/32, Nearest/Lanczos3,
and differences up to 40. These are exploratory; we did not exhaust every
algorithm/size/filter combination or calibrate on held-out labels.

Default uncached runs are repeated three times with two threads and all threads.
The separate fresh combo speed check recomputes Vision feature prints and all
4,950 Vision distances plus SIFT evidence for the 100-photo combined set, three
times. Integrity-check and incidental hash-extraction time is excluded from
that comparison. Czkawka processes originals with its own decoder, whereas the
combo uses native sRGB/oriented previews and a Python bridge. Threads, hardware
use, preview transfer, preprocessing and work differ; speed does not imply
equal retrieval quality or universal scalability.

## Findings

The default found no groups in any dataset. None of twelve tested configurations
found more than one of the four explicitly confirmed similar pairs. The user-
accepted combo found all four. Czkawka did not group the three explicitly unrelated
72743 pairs, but sparse retrieval cannot be interpreted as better accuracy.
Alternative settings found 35561 frames 9–10, already recovered by SIFT, and
additional unlabeled groups for local review. No demonstrated reason to replace
the combo or add another hashing signal yet.

The prior pHash/dHash galleries were reviewed by the user, who found numerous
false positives and rejected adding them. The prior Vision .45+SIFT galleries
were accepted as useful. These are user decisions, not newly invented numerical
precision/recall measurements. Production integration remains a separate task.

Two benchmark tests cover safe flags and group membership/path validation.
Existing 68 regression tests and application strict Pyright passed; the separate
similarity experiment's five tests passed after timing instrumentation. Private
reports/galleries and timings are in `VisionExperiments/czkawka-comparison/`.

References: [official release](https://github.com/qarmin/czkawka/releases/tag/12.0.2),
[CLI instructions](https://github.com/qarmin/czkawka/blob/12.0.2/instructions/Instruction_CLI.md),
[released grouping implementation](https://github.com/qarmin/czkawka/blob/12.0.2/czkawka_core/src/tools/similar_images/core.rs).
