# Object/attention orientation hypothesis

Standalone, read-only trial on the photos marked orientation uncertain in the
154-photo CLI integration review. This does not change CLI orientation policy,
ranking, archives, photo bytes or the production database.

The source review contains 89 uncertain entries. Two recorded source files are
missing; they are explicitly listed in the run/report and never substituted.
The other 87 images are tested at 0/90/180/270 clockwise relative to their embedded
orientation, using local Vision revision-2 object/attention regions and revision-1
horizon angle/confidence on 768-pixel views.

Vision's VNHorizonObservation supplies an angle/transform, not a horizon-height
measurement. The yellow boundary is therefore an OpenCV image-edge proxy: longest
Canny/Hough segment spanning at least 45% of width, within 20 degrees of horizontal,
and crossing the middle 70% of image height. A building edge, tabletop or scan
border can be mistaken for a horizon. The report makes this approximation visible.
No semantic sky/ground inference is claimed.

Each treatment measures the union area of clipped region boxes below that boundary.
Boxes are rasterized without double-counting overlaps. A proposal needs at least
1% image-area evidence, a native horizon confidence >=0.5, at least two evaluable
rotations, >=65% area below the boundary, and a >=15 percentage-point lead over the
next evaluable candidate. These are fixed pre-run experimental thresholds, not
calibrated accuracy or probabilities. Missing detectors, regions or boundary
measurements remain unassessed; failures are recorded explicitly.

The report shows all four views, separate object and attention proposals, region
boxes, estimated boundaries, and below-boundary fractions. Filters isolate proposed
rotations, method disagreement or both-unassessed cases. Optional human orientation
choices export explicitly as JSON; unanswered images remain unlabeled. There is
no archive/delete action and no model-selected view becomes ground truth.

Run from the repository after compiling probe.swift with xcrun swiftc -O to a
scratch path. Use the project virtual environment:

```sh
.venv/bin/python -B experiments/orientation_saliency/run.py \
  --report ../IntegrationChecks/20261017-tier-integration/review.html \
  --helper /private/tmp/photo-orientation-saliency \
  --output /path/outside/repository/new-trial
```

Output paths refuse collisions. run.json preserves source hashes/size/mtime, source
report identity, exact policy and running/completed/failed state. Each completed
image checkpoints; failed work does not publish a completed report. Source bytes,
sizes and modification times must match before the final self-contained review.
Private measurements/previews/reports remain outside Git. Checkpoints are retained
for investigation; automatic resume is not implemented.

For the second trial, add `--include-previously-rotated`. This selects the two
photos with rotation notes in the main report in addition to the uncertain set,
uses the unchanged originals (embedded orientation as the zero-degree candidate),
and reproducibly shuffles the combined inputs with `--shuffle-seed 42` by default.
Previously selected rotations do not enter the scoring or appear as preferred
answers on the cards. Their source identities are recorded in run.json for audit.
The old trial/report is retained. Input and output counts are derived per run.
