# RestorationLab

A related but separate local film-restoration tool, preserved in this repository
because the selected restoration workflow is effectively complete and worth keeping
for occasional future rolls of old/unprocessed film. It is not a photo-utils command,
menu option, scan/folder pipeline step or dependency of the main utility.

## Selected finish

Combined moderate/regional colour correction → SCUNet real-PSNR at 75% blended
with 25% colour-corrected input → gentle luminance sharpening. Processing stays
local, retains source orientation and dimensions, and writes quality-95 JPEGs.
Original scans are never edited. This is the chosen experimental appearance, not
a calibrated reconstruction of the original scene or a recovery of missing detail.

## Versioned source and private runtime

The repository's `RestorationLab/` contains the active batch runner, read-only
collection verifier, pinned dependency snapshot, upstream SCUNet architecture and
Apache-2.0 licence, an example input list, and historical algorithm/maintenance
source. `history/` is provenance, not a set of routine commands.

The existing sibling `../RestorationLab/` remains the working private data/runtime
folder. Its virtual environment, weights, real inputs, manifests, audit inventories,
logs, reference photos and output comparisons have not been moved or committed.
Restored photographs remain in `../Restored/`. No downloads or installs happen
merely by installing or running PhotoUtilities.

By default the versioned runner finds the PhotoScans workspace above the repository,
uses `WORKSPACE/RestorationLab` as its data folder, reads its `inputs.json`, looks
for sources under `WORKSPACE/OldScans01/ROLL/FRAME.jpg`, and writes under
`WORKSPACE/Restored/ROLL/`. Use explicit paths for a different workspace.
An input file maps roll folders to JPEG stems; see [inputs.example.json](inputs.example.json).
Use a separate workspace/new output collection for a future roll or recipe.

## Run separately

From the PhotoUtilities repository, use RestorationLab's isolated Python 3.12
environment, not the main utility's Python 3.9 environment:

```sh
# Read-only model load and finite CPU/MPS inference check; no source batch needed.
../RestorationLab/.venv/bin/python -B RestorationLab/restore_batch.py --check-runtime

# Read-only checksums/shapes audit of the current private JPEG collection.
../RestorationLab/.venv/bin/python -B RestorationLab/verify.py

# Inspect configuration without loading the model.
../RestorationLab/.venv/bin/python -B RestorationLab/restore_batch.py --help

# Process/resume only when intentionally requested, with explicit workspace/data.
../RestorationLab/.venv/bin/python -B RestorationLab/restore_batch.py \
  --workspace /path/to/PhotoScans --data-dir /path/to/private/RestorationLab \
  --inputs /path/to/private/inputs.json
```

The batch runner uses restoration-manifest-current.json when present, otherwise
restoration-manifest.json. It refuses missing/changed tracked source or output
checksums and untracked filename collisions; it never replaces manually edited
results. Normal processing updates its standalone restoration manifest and review
HTML. This preserves the separate tool's existing tracking format; it does not
introduce JSON sidecars into the main CLI or write its jobs.sqlite3.

`--check` checks the selected batch manifest and weights after a model/backend
check. `verify.py` checks the separately retained current JPEG inventory against
the original batch provenance, preserving intentional later edits/rotations.
The selected historical batch contained 37 images; future input lists need not.
Optional reviewed-pilot reuse metadata/reference PNGs remain private; when absent,
the runner computes from sources. Check that a reused pilot is intended for a
particular batch before processing it.

## Reconstructing the environment

The existing private environment remains available. If rebuilding is necessary,
create a separate Python 3.12 virtual environment and install the retained
requirements-lock.txt. This is a full historical environment snapshot, separate
from PhotoUtilities requirements. Download the separately stored weights only
when rebuilding is explicitly needed; see [vendor provenance](vendor/README.md).
No model weights are in Git. Preserve the upstream licence and notices.

## Limits and preservation

The model is a real-image denoiser, not a film-specific reconstruction model. Colour
correction may change real colours; detail may be smoothed or altered. The runner
checks finite output and CPU/MPS agreement and falls back to CPU when required.
Retain originals and inspect results. Historical code may refer to retired paths;
never run cleanup snapshots casually. Preserve private provenance and manifests
with their image collections. This tool is maintained for reproducibility and
occasional use, rather than expanded into the normal photo workflow.

## Preservation verification — October 17, 2026

The versioned runner's help and syntax checks passed. The existing isolated
runtime loaded the retained SCUNet weights and produced finite CPU inference;
maximum CPU/backend difference was 0.0. A disposable synthetic collection verified
the collection-audit entry point and changed-source refusal.

A full audit of the historical private collection currently stops at a missing
source path recorded under OldScans01. The private manifests were not rewritten
or redirected to similarly named consolidated samples. Restore the intended source
paths or explicitly reconcile provenance before a full batch audit/resume; retaining
the code does not establish that every historical input remains available today.
