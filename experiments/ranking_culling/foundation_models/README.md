# Local Vision / Foundation Models triage experiment

Standalone experimental implementation on `experiment/ranking-culling`.
Authorized October 13, 2026 after the OS upgrade. Production grouping, focus
rules, CLI, archive workflow, database and original photo metadata are unchanged.
Private reports, model views and explicit JSON exports must remain outside Git.

## Verified platform and access

macOS 27.0.1 build 26A434; Command Line Tools SDK 27.0; Swift 6.4;
Apple A18 Pro, Mac17,5, 8 GiB. Full Xcode is not required for these helpers.
The CLI legal notice was accepted by the user, not by this experiment.

`SystemLanguageModel.default` reports available, vision and guided generation,
with variant AFM 3 Core. `fm respond --model system` is the on-device backend.
No PCC, hosted endpoint, OCR/barcode tools, model substitution or server is used.
Native image-buffer initialization fails inside the agent's general sandbox;
actual Vision and Foundation Models inference was tested with native-service
access outside it. These failures remain in separate private diagnostic runs.

The sandboxed context-size getter reported zero; the actual native-access pilot
reports 4096 tokens. One-to-four-image gates succeeded. Image token costs and
larger-group context exhaustion still need measurement.
The CLI's `--label` flag is reserved for image-using OCR/barcode tools, so this
experiment uses explicit ordered text/image pairs and validates every returned ID.

## Build

From the repository root:

```sh
xcrun swiftc -O -module-cache-path /private/tmp/photo-triage-module-cache \
  experiments/ranking_culling/foundation_models/vision_probe.swift \
  -o /private/tmp/photo-triage-vision
xcrun swiftc -O -module-cache-path /private/tmp/photo-triage-module-cache \
  experiments/ranking_culling/foundation_models/decode_view.swift \
  -o /private/tmp/photo-triage-decode
xcrun swiftc -module-cache-path /private/tmp/photo-triage-module-cache \
  experiments/ranking_culling/foundation_models/capabilities.swift \
  -o /private/tmp/photo-triage-capabilities
```

`vision_run.py --help` documents baseline/solo export inputs, native helper and
new external output directory. Explicit `--exclude-baseline-index` options may
exclude only user-confirmed removals. Unknown missing/changed originals stop
preparation. Solo sampling takes up to 30 nonmembers of saved groups from the
supplied cached export; it does not change grouping or claim that nonmembers
are inferior photos. Future larger evaluation should broaden source folders.

`vision_probe.swift` tests image classification revision 2, face capture quality
revision 3, facial landmarks revision 3, people/animals and attention/objectness
saliency revision 2. It records individual request failures and full observations
at oriented 1024/2048 views. These are measurements, not interesting/cull labels.
The older `VN` APIs remain supported; these capabilities are not all new to 27.
Raw classification labels are broad diagnostics, not automatic portable tags.

The macOS 27 `GenerateIterativeSegmentationRequest` is investigated separately
by `segmentation_probe.swift`; its asset status must be checked before inference.
It does not modify existing focus ROIs or thresholds.

## Foundation Models execution

```sh
.venv/bin/python -B experiments/ranking_culling/foundation_models/fm_run.py \
  --manifest /path/outside/repo/vision-run/manifest.json \
  --decoder /private/tmp/photo-triage-decode \
  --schema experiments/ranking_culling/foundation_models/assessment-schema-strict.json \
  --capabilities /private/tmp/photo-triage-capabilities \
  --output /path/outside/repo/new-fm-run --gates-only
```

Omit `--gates-only` for individual general/scene-aware assessment and bounded
related-image comparisons. `--reuse-gates` accepts a compatible completed gate
export. A historical manifest containing confirmed missing duplicate records
requires explicit `--exclude-known-removed-index` for each baseline index.
New manifests exclude those records at preparation time instead.

Every image has independent interest and problem-review fields. Multiple strong
images and overlaps are valid. No-clear-interest never invokes archive/delete.
General and scene-aware prompts are separate treatments; human preferences and
prior aesthetic scores are withheld. All results remain advisory.

The decoder creates separate upright 8-bit sRGB PNG model views, preserving
aspect ratio and never upscaling. Source hashes are checked before/after;
transform metadata and exact view hashes are recorded. Refuse occupied output
directories/files. Calls run serially, have timeouts and checkpoint after every
response. Native invalid image gates stop dependent inference. Failed Vision requests stop
dependent preparation after saving the completed diagnostic rows. Per-call response
validation failures remain explicit and do not acquire neutral quality labels.
Reruns use new directories; automatic interruption resume is not implemented.

Whole six-image comparison is tested separately when available. Larger groups
use subsets up to four, with overlap for a final singleton so every member has
context. This is a diagnostic strategy; it does not claim whole-group equivalence
or discard candidates by a pairwise tournament.

A client-level `sandbox-exec` network-denied image call succeeded. End-to-end
inference with networking disabled for all service processes remains unverified.
The pilot explicitly selects only the on-device system model; no cloud fallback
exists. Child-process RSS excludes Apple model daemon/unified-memory allocation.
System memory pressure is a contextual observation, not model-specific usage.

## Report / human review

```sh
.venv/bin/python -B experiments/ranking_culling/foundation_models/report.py \
  --results /path/to/fm-run/results.json --vision /path/to/vision-run/vision-results.json
```

Writes `review.html` and `summary.json` beside results. Suggestions start hidden;
reveal them after independent judgments where possible. Grouped/solo filters,
interest/keep/cull labels and notes are available. Export labels before closing;
there is no automatic browser persistence. Exports record whether the model was
revealed when a label changed. Model reasons are escaped; no image mutations or
metadata writes are available. Historical human preferences remain separate.
The report reuses prior previews, while exact model-view PNGs remain in the run.
Vision boxes use normalized top-left coordinates; face landmark points retain
face-local bottom-left coordinates and are not shown as global overlays.

Summary reports interest/problem distributions, matched-condition changes,
context changes, execution time and failures. No human-agreement or false-reject
accuracy is claimed before new multi-choice/solo human labels are supplied.
Prior favorite labels cannot stand in for complete keep/cull ground truth.

## Verification

```sh
.venv/bin/python -B -m unittest discover -s experiments/ranking_culling/foundation_models -v
.venv/bin/python -B experiments/ranking_culling/foundation_models/native_checks.py \
  --helper /private/tmp/photo-triage-vision --decoder /private/tmp/photo-triage-decode
```

Synthetic native checks cover JPEG/PNG/single TIFF, orientation 6, no upscaling,
multipage/corrupt/missing/BMP failures, all seven requests, collision refusal and
unchanged source bytes. Protocol tests cover invalid/missing/duplicate IDs,
controlled values, bounded tags and overlapping interest/problem judgments.
The existing 101-test regression suite and strict application Pyright passed;
30 aesthetics tests passed. The loopback regression needs networking permission
for its temporary local test server, independently of inference networking.

## Metadata recommendation, provisional

Keep scene, AI recommendation and explicit workflow status separate. Prefer
standard `XMP-dc:Subject` for portable flat keywords; synchronize `IPTC:Keywords`
on supported exported JPEG/TIFF copies when needed. Test `XMP-xmp:Rating` only
under a separately confirmed user policy; never overwrite existing ratings.
XMP sidecars preserve originals but actual application import/search compatibility
must be verified. Finder tags are a separate filesystem mechanism, not a proven
Photos keyword transport. Avoid a hierarchical taxonomy until an actual workflow
needs it. RAW/DNG behavior remains untested.

Disposable synthetic JPEG/HEIC/TIFF/PNG tests verified ExifTool read/write of XMP
keywords and rating 4, and IPTC keywords on JPEG/TIFF, with identical decoded
pixels before/after. XMP sidecar creation succeeded. No private originals or
live photo libraries were modified. This is file-layer verification only.

Apple documents keyword assignment and search in Photos:
https://support.apple.com/en-lamr/guide/photos/pht8d0ad5198/mac
The installed macOS 27 Photos SDK additionally declares public asset rating,
`addKeyword`/`removeKeyword` and extended-metadata keyword APIs. These offer a
future documented local integration route; no Photos permission was requested,
no API calls against a library were made, and interoperability is not established.
Photos/Photomator import, search, export and rating round trips remain pending.

Official API context:
https://developer.apple.com/videos/play/wwdc2026/241/
https://developer.apple.com/videos/play/wwdc2026/237/

The later diagnostic `--supplementary-only --vision /path/to/vision-results.json`
condition supplies face capture observations, people/animal detections and
existing focus warnings for a small deterministic sample. It needs compatible
`--reuse-gates` provenance. This condition stays separate from independent
image-only results and never changes a focus flag or archive decision.

`test_report_controls.cjs /path/to/review.html` checks the generated static JS
with a fake DOM: hidden suggestions, label export/exposure provenance, filters
and optional overlays. Report summary tests ensure failed calls do not become
neutral labels and scene-context changes use the matching scene baseline.


## Schema reliability finding

The baseline `assessment-schema.json` described allowed string values but did
not constrain them as enums. One pilot group call returned an unlisted value;
a repeat returned `street_scene` instead of `urban`. A Vision-supplement call
copied `low_global_detail` into the problem-review enum. These calls were rejected,
not normalized or converted to neutral assessments. The baseline's first failed
raw response was lost by its error-handler overwrite; the follow-up retains raw
responses and reproduces the vocabulary issue. Future helpers preserve raw output
on validation failures.

`assessment-schema-strict.json` adds actual enum constraints. Its two-image retest
passed without changing the photographic prompt. Use it for future runs; its
schema hash differs, so old gate results cannot be silently reused. This improves
protocol reliability, not photographic discrimination. Baseline results remain
unchanged and should not be pooled with stricter-schema trials without provenance.


## Initial execution findings

The private pilot covered 63 grouped images in 20 active groups and 30 saved
ungrouped images. Image-only general assessment highlighted 93/93; scene-aware
assessment highlighted 92/93 with one maybe. Neither identified a
`possible_problem`; general had four uncertain problem reviews and scene-aware
had three. Scene labels changed on 10/93 matched inputs. Group context did not
change matched independent interest labels. This is insufficient discrimination
for review-workload reduction, not validated photographic accuracy.

The main pilot completed 231 attempted calls: 230 valid assessments and one
controlled-vocabulary failure, in about 32.9 minutes. Successful-call median
latency was 6.9 seconds; the six-image comparison took 23.7 seconds. Peak child
RSS was about 68.3 MiB, excluding model services. One system pressure snapshot
reported 51% free; cumulative swap counters cannot be attributed to the pilot.

The separate Vision-supplement sample had six calls, five valid and one invalid.
All valid results remained interesting; one flagged an existing focus concern.
This does not establish added accuracy. Two strict-schema follow-ups are kept
separate from baseline results.

Iterative segmentation succeeded on three 1024-long-edge model views with central
seeds and balanced quality. Inference timings were approximately 3.47, 0.26 and
0.21 seconds after request asset setup. The specific configured request needed
`downloadAssets()` before readiness; an earlier download on a different request
was insufficient for those initial attempts. Download/setup time is not included
in these inference timings. Masks and input checksums were retained in a separate
private report. Correct intended-subject segmentation remains a human judgment;
these masks are not integrated into focus measurements.

Recommendation: retain the standalone experiment and strict-schema validation;
do not integrate current interest prompts into production. Review a small blind
sample including solos, then define stronger editing-candidate versus ordinary
alternative anchors without quotas. Freeze revised prompts before evaluating a
separate held-out set. Existing native focus warnings remain independent. No
personalized model or Qwen installation is justified by this pilot alone.


Add `--supplement /path/to/supplement/results.json` when generating the review
to show the separate Vision-evidence condition. It must match manifest provenance;
baseline summary metrics remain separate. The strict-schema technical-evidence
retest also passed, retaining an uncertain problem review rather than silently
converting the old invalid technical code. Metadata file-layer checks are
reproducible with `metadata_checks.py --output NEW_EXTERNAL_DIR --decoder HELPER`.


`--human-labels /path/to/prior-labels.json` adds separately revealed historical
preferences after validating the baseline experiment identity. Prior choices and
notes are preserved; other group members are not treated as rejected. A human
photographic-type selector supports later classification assessment alongside
interest/keep/cull judgments. No human labels are sent to the model.

Human Worth keeping is the sole yes/no keep/cull control. Exports derive cull
as the inverse of keep, while an unanswered keep leaves both fields unjudged.
Older exports that only populate keep can use the same interpretation. This
is a review label, not an archive instruction.

## Evaluate a new human export

```sh
.venv/bin/python -B experiments/ranking_culling/foundation_models/evaluate_human.py \
  --human /path/to/exported-human-labels.json \
  --results /path/to/pilot/results.json --output /path/to/new-private-evaluation
```

Validates manifest hash and image inventory, preserves the original export
byte-for-byte, and writes evaluation.json, findings.md and comparison.html
outside Git. Blank interest remains unjudged even when Keep is No or notes
mention technical trouble. Keep determines the inverse cull label; contradictory
flags fail validation. Comments never authorize file actions. Editing interest
and retention for memories are independent. Primary scene comparisons are literal
matches, not a universal classification truth. Evaluator boundary tests also
cover these distinctions; the standalone suite now has 11 passing tests.

## Revised prompt and detection audit

Add `--prompt-file experiments/ranking_culling/foundation_models/prompts/editing_candidates_v2.txt`
with the strict schema for the revised editing-candidate experiment. The complete
effective prompt is saved in results; old prompt gates are incompatible. The
revised prompt is implemented as an option, not yet evaluated in a new model run.

`audit_detection.py --human EXPORT --results PILOT_RESULTS --vision VISION_RESULTS
--output NEW_EXTERNAL_DIR` compares human portrait/group-portrait labels and
explicit face/head/people/glasses comments with cached human-face/person counts
at both resolutions. It creates a private overlay report. Failed detections are
unknown rather than zero; every cached path is checked against the image mapping.
The human labels supply requested count expectations, not verified per-face
annotations. Dog-face comments need separate animal evidence. Audit tests bring
the standalone suite to 14 passing tests.

## Raw face-capture score ordering (latest user direction)

`face_score_report.py --results PILOT_RESULTS --vision VISION_RESULTS --output
NEW_EXTERNAL_DIR` creates a separate local report using the maximum native human
face-capture score per image at 2048. Existing groups are reordered descending;
exact ties remain stable. No-face, failed and missing quality are unassessed, not
zero. All images and memberships are retained. The report exposes all raw face
scores, including the selected maximum. No model inference or photo mutation runs.

The solo cutoff starts unset, as requested pending distribution review. Choosing
it interactively previews interesting-solo highlights and exports the explicit
cutoff plus selected IDs. It does not overwrite old Foundation Models interest
labels, human choices or production metadata. Native face-capture quality is the
chosen capture-quality signal, not a renamed pure-focus score. The unused v3
subject-focus prompt is superseded by this simpler experiment for ordering.

## Cascade sample review

`cascade_probe.swift` measures Apple Vision revision-1 aesthetic/utility scores
and Core Image blink/smile features on upright cached 1024 views. Run locally;
Vision may require execution outside the agent sandbox. Expression features are
independent detections, not face identities matched to Vision. Missing eye
positions are unassessed.

`cascade_report.py --root EXTERNAL_EXPERIMENTS --native NATIVE_JSONL --output
NEW_EXTERNAL_DIR` combines those results with the existing detail, exposure,
2048 face-quality and saliency-layout diagnostics. The report documents every
provisional rule, preserves all images, orders each original similarity group,
and ranks solos within the full 93-image reference. Flags are review suggestions,
not deletion selections. No forced drop counts or production integration occur.
The output saves native measurements, ordered JSON and self-contained HTML.
Four synthetic policy tests check unknown faces, expression alternatives, joint
detail thresholds, comparison kinds and percentile ties.

### Three-tier report from saved measurements

`tier_report.py --baseline PRIOR_CASCADE_RESULTS --pilot PILOT_RESULTS --output
NEW_EXTERNAL_DIR` generates Top Pick / Review / Possible Cull without rescanning
or running inference. Top Picks need a documented face-quality or joint-detail
advantage; no forced quotas. Composition-only flags become advisories. Solos use
the full sample as their reference, with the exceptional face cutoff still unset.
Saved results include exact policy, input checksum, full-sample arithmetic ranking
and before/after tier transitions. The HTML preserves all groups and images and
shows the supporting reasons. Six synthetic tests cover conservative promotion,
missing faces, low-detail guards, composition advisories and full-sample solos.
