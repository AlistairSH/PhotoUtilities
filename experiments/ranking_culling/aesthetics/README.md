# Isolated Apple Vision aesthetics experiment

This standalone experiment is authorized on `experiment/ranking-culling` only.
It does not change CLI commands, grouping thresholds, focus policies, canonical
SQLite, archives, or original photographs. No dependencies/model downloads were
added. The macOS frameworks run locally; previews and measurements stay outside Git.

## Native API and orientation

`scorer.swift` uses `VNCalculateImageAestheticsScoresRequest`, revision 1, and
`VNImageAestheticsScoresObservation.overallScore` / `.isUtility`. The installed
SDK declares macOS 15+ availability; verified on Apple Silicon macOS 26.6.2.
Apple documents overallScore as an overall assessment incorporating aesthetic,
failure and utility signals, from −1 (least desirable) to 1 (most desirable).
It is not a probability or a component-level composition/expression/lighting
measurement. `isUtility` indicates potentially unmemorable/unexciting content,
not necessarily poor technical image quality. No extra component scores are invented.

Official references:
- https://developer.apple.com/documentation/vision/vncalculateimageaestheticsscoresrequest
- https://developer.apple.com/documentation/vision/vnimageaestheticsscoresobservation/overallscore
- https://developer.apple.com/documentation/vision/vnimageaestheticsscoresobservation/isutility

ImageIO checks the supported image type and single-image count. Vision receives
the original file URL and its explicit EXIF orientation (default up), with no
thumbnail substituted for scoring. Separate ImageIO transform-aware 1200-pixel
JPEG previews are for review only. Each input runs in an autorelease pool and
emits one JSON line; failures retain the path/error rather than masquerading as
a valid low score. JPEG/HEIC were exercised on real samples; JPEG/PNG/single TIFF,
EXIF orientation 6, corrupt/missing/BMP/multi-TIFF cases use synthetic smoke checks.

## Run

From the repository, compile to a local temporary path:

```sh
xcrun swiftc -O -module-cache-path /private/tmp/photo-aesthetics-modules \
  experiments/ranking_culling/aesthetics/scorer.swift -o /private/tmp/photo-aesthetics
.venv/bin/python -B experiments/ranking_culling/aesthetics/experiment.py \
  --folder /path/to/BestPhotoSamples --helper /private/tmp/photo-aesthetics \
  --output-dir /path/outside/repository/new-aesthetics-trial
```

The output directory must be new and outside the repository. Shallow original
inputs reuse the accepted similarity/focus engine. Exact content matches to
existing assets are read from the configured database in read-only mode; copied
photos get historical asset references, never invented new IDs. New sample group
IDs are local to the experiment; they are not claimed to be prior SQLite groups.
Chaining is preserved. Full pair evidence, existing focus measurements and hashes
are retained in `grouping.json` / `results.json`. All source SHA-256 hashes are
checked before/after. `run.json` records running/completed/failed/interrupted
status; score checkpoints survive failure. Interrupted/incomplete runs never
publish a review report. Re-run into a new directory; automatic resume is not
implemented. A native timeout kills the helper and marks the run failed.

## Comparison policy

A sorts candidates by raw score. C keeps the same order and shows advisory focus
flags. Lack of a flag means unassessed, not verified sharp.

B is a deliberately narrow experiment: only fully directly matched groups with
no weak (`potential`) pair evidence may exclude an image. The existing comparison
must identify it as `softer`, with a directly matched, successfully scored
`sharper` competitor retained. Existing measurements require comparable region
kind/count/area, both Laplacian and Tenengrad ≥1.5× at both resolutions. Those
thresholds are reused unchanged. No general review flag alone excludes an image,
and no comparison propagates transitively. This remains heuristic evidence,
not a verified absolute blur verdict.

Any missing direct match or potential pair flags the whole group for manual
review. These groups retain rankings, but all approaches withhold a single-winner
recommendation. Incomplete scoring and exact top-score ties also withhold it.
Nonzero small gaps are shown without any validated confidence claim or arbitrary
weak/clear threshold. All tied candidates use original index order for display
ranking only. Scores never determine the blind preview order.

## Human review and export

Open `review.html` directly in a normal browser. Each group has large previews,
source links, a preferred-image/No-clear-winner choice, optional human category
and notes. Scores and focus advice start hidden. Select independently, then
Reveal. The first pre-reveal choice is frozen for subsequent analysis; later
edits are flagged. Do not inspect `results.json` before blind choices.

Selections are saved in browser localStorage where permitted. An explicit
message reports storage failure; **export JSON before closing** even when
storage works. Export downloads `aesthetics-evaluations.json`. Import restores a
saved export from this exact experiment. File-URL storage behavior differs by
browser; export is the portable source of truth. No loopback service is needed.
No Delete, Archive or Restore controls exist here.

Provide the exported file to compare your judgments. Run:

```sh
.venv/bin/python -B experiments/ranking_culling/aesthetics/evaluate.py \
  --results /path/to/trial/results.json \
  --evaluations /path/to/aesthetics-evaluations.json \
  --output /path/to/new-evaluation-summary.json
```

The evaluator rejects other experiment IDs and invalid group/member selections.
It measures A/B/C top-1 and top-2 candidate agreement, recommendation coverage
and agreement, no-winner counts, optional human category agreement, focus-induced
winner changes/improvements/worsening, and gap/agree cases for later study.
No-winner selections are reported separately, excluded from image-choice rate
denominators; withheld groups still contribute to candidate ranking rates but
not recommendation agreement. Original blind choices take precedence. No human
agreement or calibrated gap thresholds are claimed before real judgments exist.

## Verification

```sh
.venv/bin/python -B -m unittest discover -s experiments/ranking_culling/aesthetics -q
.venv/bin/python -B experiments/ranking_culling/aesthetics/test_native.py \
  --helper /private/tmp/photo-aesthetics
.venv/bin/python -B -m unittest discover -q
.venv/bin/python -B -m unittest discover -s experiments/ranking_culling -p 'test_*.py' -q
.venv/bin/pyright
```

The native helper and existing loopback test can require execution beyond the
agent sandbox. `test_controls.cjs PATH_TO_SYNTHETIC_REPORT` uses Node's VM and a
fake DOM to check generated selection/storage/export logic without browser or
network access. A browser visual check was unavailable because the browser tool
blocks local-file URLs; do not claim it was performed. Pyright's existing strict
configuration covers application modules; experimental Python is covered by its
separate tests, not that type-check configuration.

Initial measured diagnostics are in the private output folder's `FINDINGS.md`.
Wait for human selections before choosing A/B/C, setting confidence thresholds,
or assessing a second model. Integration, downloads of alternative model weights,
and any push/merge remain separate decisions; no production integration here.

## Human-confirmed expanded sets and disagreement audit

`expanded.py` consumes an existing results file, its matching human evaluation
export, and explicit membership corrections. It preserves the baseline, original
group IDs and direct-pair evidence, recomputes existing pairwise focus highlights
inside the human sets, and reruns original-file Apple scores with checksum checks.
A separate experiment ID prevents old choices from being treated as judgments of
the newly expanded sets. Its four-group report supports fresh selections/export;
a separate revealed mismatch report compares old human choices and Apple tops.

```sh
.venv/bin/python -B experiments/ranking_culling/aesthetics/expanded.py \
  --results /path/to/original/results.json \
  --corrections /path/to/membership-corrections.json \
  --labels /path/to/original/human-evaluations.json \
  --helper /private/tmp/photo-aesthetics \
  --output-dir /path/outside/repository/new-expanded-trial
```

Use the new trial's `expanded-review-results.json` with the evaluator when new
labels arrive. Previously viewed scores mean follow-up selections cannot be
claimed to be fully independent blind judgments. The mismatch analysis reports
pair/larger-set agreement separately, mathematical random-ranking reference
levels, raw gaps, human score deficits, focus flags and literal human notes.
It does not infer the model's reasons, reclassify user categories or fit weights.

`orientation_audit.swift` is a separate native diagnostic comparing original
URL+EXIF requests, full-size ImageIO source pixels+EXIF, and full-size ImageIO
transform-aware pixels+.up. It writes measurements only. Differences can involve
image representation as well as orientation; they do not alone establish an EXIF
bug or justify replacing the original-file baseline. Compile with the same
Swift command as scorer.swift, substituting its source/output name. Pass a JSON
array of original paths on stdin. No thumbnails from an earlier report are used.

## Reduced blind preference retest

`blind_pairs.py` prepares only reviewed disagreements with specific human choices:
previous human pick versus raw Apple top. It skips already agreeing sets and
No-clear-winner labels without inventing an image choice. A cryptographic system
random generator shuffles both pair sequence and A/B positions. The report
contains anonymous pair IDs and embedded previews only, without filenames,
original group IDs, source links, scores, or origin mappings. A separate private
answer-key file enables later evaluation; it is never embedded in the HTML.
The new UUID separates browser storage/exports from previous rounds. The static
report allows enlargement, selection/No-clear-preference, optional notes,
import/export and visible browser-storage status. Reduced-set choices measure
preference consistency under prior exposure, not independent model accuracy.
No other image candidates are included in this report. Source hashes are verified
and originals remain unchanged. `evaluate(key, labels)` checks the identity and
reports repeated previous choices versus Apple tops after the export arrives.

The user's reviewed conclusion is advisory-only: native aesthetics can help
compare photographs, but must not be presented as a true winner. Side-by-side
review helps expose tradeoffs; emotional or contextual preference can remain
stable even when another image appears technically preferable. Native model
reasons are not observable from overallScore/isUtility. Further integration is
still deferred; retain manual preference and no-clear-preference controls.

## Native face-capture-quality experiment

`face_quality.swift` uses VNDetectFaceCaptureQualityRequest revision 3 on original
URLs with explicit EXIF orientation. It emits every detected face's native quality,
box and detection confidence; no aesthetic scores or pixels are recalculated.
No-face and null-quality inputs remain unassessed. `face_comparison.py` compares
existing choices with maximum minimum-face quality and records a mean sensitivity
check; these are experimental aggregations, not native whole-image scores.
Different detected counts and aggregation disagreement must remain visible.
Quality is intended for repeated captures of the same face/person; subject
correspondence is not established by this experiment. No change to production
focus, grouping, quality thresholds, automatic culling or CLI integration.

## Schuhmann / CLIP alternative ranking

The user authorized installing and testing Christoph Schuhmann's predictor.
`schuhmann.py` uses the original `sac+logos+ava1-l14-linearMSE.pth` architecture
(768→1024→128→64→16→1 with the original dropout, no added activations) and official
CLIP ViT-L/14 image features, normalized to unit length. Models use float32 eval
mode. Predictor state loading uses `weights_only=True` and strict key checking.
The official CLIP checkpoint is loaded from a local file, with its published
SHA-256 verified at download. No training packages or cloud image inference.

A separate Python 3.12 environment and model cache live outside the repository;
the existing Python 3.9 production environment remains unchanged. Runtime/model
versions, public download URLs, licenses, sizes/hashes and a dependency freeze
are retained with that private experimental runtime. CLIP source is pinned to
`d05afc436d78f1c48dc0dbf8e5980a9d471f35f6`. The scorer tests three dispersed CPU/MPS
pilot images at a fixed 0.001 numerical verification tolerance and uses MPS when
they pass; otherwise it records the reason and uses CPU. This tolerance is not
aesthetic confidence calibration. A selected-device repeat check is recorded.

`decode_original.swift` reads each original through ImageIO, applies embedded
orientation, converts full-size pixels into 8-bit sRGB and writes one temporary
lossless PNG. It refuses occupied outputs and unsupported/multiple images.
Only one PNG exists at a time and it is removed after preprocessing. These are
original-derived analysis inputs, not earlier report thumbnails. Official CLIP
preprocessing resizes the short side and center-crops to 224×224, then normalizes
channels. The report exposes that exact model view beside each compared image.
Do not silently replace center cropping with padding or change the checkpoint
preprocessing after seeing human labels.

```sh
xcrun swiftc -O -module-cache-path /private/tmp/photo-aesthetics-modules \
  experiments/ranking_culling/aesthetics/decode_original.swift \
  -o /private/tmp/photo-schuhmann-decode
/path/to/isolated-venv/bin/python -B experiments/ranking_culling/aesthetics/schuhmann.py \
  --results /path/to/expanded/results.json --labels /path/to/latest-human-labels.json \
  --clip-weights /path/to/local/ViT-L-14.pt \
  --head-weights '/path/to/local/sac+logos+ava1-l14-linearMSE.pth' \
  --decoder /private/tmp/photo-schuhmann-decode \
  --output-dir /path/outside/repository/new-schuhmann-trial
```

Scores are kept in native units and only sorted within existing groups, with
human, Apple and Schuhmann comparisons. No normalization onto Apple's range,
weighted merging or true-winner claim. Missing originals are recorded as missing,
not given zero scores. Incomplete/weak/chained sets and exact ties withhold a
suggested leader while retaining available raw rankings. Source hashes are
verified before/after; outputs checkpoint and distinguish failed/interrupted
runs. Inference requires only previously downloaded local weights.

Next-phase idea recorded by the user: rsinema's seven component scores could
support a radar chart of the *same component axes* for human-, Apple- and
Schuhmann-selected images in small groups. Deduplicate images when picks coincide
and label their multiple roles. Do not use three unrelated overall-score scales
as radar axes, invent component measurements for Apple/Schuhmann, or imply radar
area is an objective winner. rsinema implementation/weights still need auditing
and no rsinema scores or charts are generated in this phase.

Upstream sources: https://github.com/christophschuhmann/improved-aesthetic-predictor
(Apache-2.0) and https://github.com/openai/CLIP (MIT). Mac compatibility and observed
performance are recorded in the trial's private findings, not assumed from CUDA
examples. The upstream CLIP checkpoint currently loads through torch.jit.load;
PyTorch emits a deprecation warning, but execution results are verified locally.

## rsinema seven-component test

The user authorized a diagnostic trial before deciding whether to use rsinema
in the review workflow. `rsinema.py` loads the pinned public `model.pt` as a
weights-only state dictionary, reconstructs the declared CLIP ViT-B/32 backbone
and seven published linear heads, and requires every key/tensor to match.
The checkpoint contains the vision-transformer backbone directly rather than
an entire model object. The upstream `torch.load(remote-looking-path)` example
is not directly runnable; the experiment uses local downloaded weights/config
and supports the differing Transformers backbone layouts with strict matching.
No unverified missing layers are initialized as a substitute.

The heads, in published order, are overall aesthetic, technical quality,
composition, lighting, color harmony, depth of field and content. Their labels,
training-on-PARA claim and 0–5 scale come from the author, not independent
validation. All actual outputs are retained without clipping/remapping; charts
are withheld if the measured values violate that scale. Original file bytes are
checked before/after. Missing originals remain missing, not zero-rated photos.

This experiment reuses the full-size ImageIO upright sRGB decoder from the
Schuhmann trial; the locally cached published CLIP image processor then applies
its specified 224×224 center crop and normalization. Offline Hugging Face flags
and disabled telemetry are set before importing the loader. No processor/model
requests use remote identifiers during private inference. CPU/MPS pilot vectors
and a selected-device repeat check are recorded.

```sh
/path/to/isolated-venv/bin/python -B experiments/ranking_culling/aesthetics/rsinema.py \
  --results /path/to/expanded/results.json --labels /path/to/latest-human-labels.json \
  --schuhmann /path/to/schuhmann/results.json --model-dir /path/to/local/rsinema-models \
  --decoder /private/tmp/photo-schuhmann-decode \
  --output-dir /path/outside/repository/new-rsinema-trial
```

The report reuses human, Apple and Schuhmann picks, deduplicates coincident picks,
and presents component tables in Apple-score order. Optional diagnostic radar
charts are rendered with Matplotlib on fixed shared 0–5 axes; the chart area is
not a winner metric. Charts use only rsinema components of the picked images,
not unrelated Apple/Schuhmann scalar scores. Actual model-view crops are visible.
Global and within-group-centered component correlations assess whether the
heads mostly move together; exploratory agreement per axis is recorded without
fitting weights or selecting the strongest head after seeing labels.

The future user-proposed review design is Apple-ordered groups, a Schuhmann-top
highlight, manual favorite selection and optional rsinema chart for the resulting
2–3 distinct picked images. This trial does not implement that production workflow,
modify accepted grouping/focus reports or ask for another human scoring round.
