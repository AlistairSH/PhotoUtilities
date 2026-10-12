> Historical development scripts and tests retained for reproducibility. The
> adopted CLI path is documented in the repository README and implemented in
> photo_utils/focus*. Rejected landmark/patch/other filter experiments are not
> additional production review rules. Generated data stays outside Git.

# Experimental focus ranking

Ranking and initial culling review sampling are standalone experiments. Ranking reads a completed
production similarity job from SQLite in read-only mode. It preserves group
membership, pair evidence, and unmatched images. No new similarity algorithm,
production command, database migration, or production module changes.

## Run

From the repository root, using the existing virtual environment:

```sh
xcrun swiftc -O -module-cache-path /private/tmp/photo-focus-modules \
  experiments/ranking_culling/faces.swift -o /private/tmp/photo-focus-faces
.venv/bin/python experiments/ranking_culling/run.py \
  --job SIMILARITY_JOB_ID --helper /private/tmp/photo-focus-faces \
  --output-dir /path/to/new-experiment-output --export-analysis
```

The output directory must be new, outside the repository and source image
directories. The default database is the existing PhotoUtilities jobs.sqlite3;
`--database` selects a different existing database. Source hashes must still
match the saved grouping run, and are rechecked before publication. Image input
symlinks are refused. Native decoding/detection failure aborts the run.

Outputs: self-contained `ranking.html`, `review.csv` with blank human-choice,
agreement and notes columns, and explicitly requested `analysis.json` containing
raw measurements, thumbnails, group decisions, hashes and implementation key.
This export is private and belongs outside Git. No original image is written,
no routine database is created or changed, and no culling verdict is generated.

To change ranking rules and regenerate without repeating Vision, add
`--reuse-analysis /path/to/previous/analysis.json`, with a new output directory.
Reuse requires identical source hashes, ordered paths, measurement implementation
key and settings. Ranking code is deliberately excluded from that key. The
native helper must be rebuilt whenever faces.swift changes.

## Measurements and decisions

`faces.swift` adapts the production ImageIO/CoreGraphics decoder: oriented
single-image preview, up to 1024 pixels, 8-bit sRGB RGBA. It runs local Vision
face rectangles on those exact pixels. Normalized boxes use top-left coordinates.
No new dependencies: existing NumPy and OpenCV implement Laplacian variance and
mean squared Sobel-gradient magnitude (Tenengrad).

`quality.py` returns measurements without recommendations, reusable for future
culling: raw and sigma-1 Gaussian-smoothed global and face metrics at 1024 and
512 maximum dimensions, luminance mean/spread and a 4×4 smoothed edge distribution.
Images are never upscaled. Faces smaller than 24 pixels on either side, or with
Vision detection confidence below .5, are excluded. Detection confidence is a
Vision observation field, not a focus probability. Settings are provisional.

`ranking.py` uses face measurements only when every group member has equal,
nonzero usable face counts at each scale. Otherwise it applies global metrics
consistently and marks the subject recommendation uncertain. Equal face counts
do not establish matching identities; human review remains necessary.
Face scoring starts at 60% average + 40% minimum; alternatives using minimum
alone and average alone are exported for comparison. Face prominence weighting,
eye landmarks, people/animals and saliency are future experiments.

Within a group, each smoothed metric is divided by that group's maximum for the
same metric/scale. Four relative values receive equal weight. Zero-valued metrics
produce zeros, not invented quality evidence. The first image in descending order
is a provisional suggestion; ties retain original member order. A score gap ≤.10,
disagreement among raw/smoothed/scale winners, or missing comparable faces marks
the result uncertain. These are hypotheses, not calibrated probabilities.

Grain suppression can erase real detail; raw/smoothed disagreement indicates
sensitivity rather than proof of grain. Texture, contrast, exposure, scan
sharpening, subject scale, compression, low texture, borders, and missed faces
can mislead either metric. Face boxes include background/hair, not just eyes.
No universal blur threshold or cross-material comparison is justified yet.

The report reuses the production HTML renderer without changing it. Members are
ordered, provisional first choices outlined, uncertain explanations visible,
and measurements expandable. Use review.csv to record your actual choice and
failures; synthetic tests alone do not validate real-photo recommendations.

```sh
.venv/bin/python -B -m unittest discover -s experiments/ranking_culling -v
```

## Culling review experiment

The user requested switching to culling after finding grouped ranking unhelpful.
`culling.py` consumes the same shared measurement records, with separate decision
logic. `cull_run.py` reviews every image in each explicit export, regardless of
similarity membership. It reuses the recorded pixels/measurements without
Vision calls, with checksum and measurement-implementation verification.

```sh
.venv/bin/python experiments/ranking_culling/cull_run.py \
  /path/to/batch-one/analysis.json /path/to/batch-two/analysis.json \
  --output-dir /path/to/new-culling-output
```

Each input export is a separate reference batch, not a calibrated material
profile. All six signals (smoothed global Laplacian, global Tenengrad and maximum
4×4-tile Tenengrad, at both scales) must be in that batch's lowest 10% to enter
the review shortlist. Tied values count conservatively; a constant batch cannot
produce a forced quota. Fewer than 20 images disables this sampling rule. A
relatively sharp local region can prevent shortlisting despite low global
detail. A small subject can still be missed inside a coarse tile.

This is a provisional review-sampling hypothesis, not a universal blur threshold.
No image is declared severely blurred or clearly acceptable. Shortlisted images
are `manual_review`; all others are `unassessed`, and every severe-blur-candidate
field is false. A roll of similar low-contrast or low-texture scenes can dominate
the shortlist. The report exposes counts by source folder to make that visible.
Grouping never changes the decision and the worst member of a group is not
automatically a candidate.

Outputs are `culling.html`, `culling-manifest.json` (raw shared focus records,
screening signals, reference rules, explanations, source checksums, versions and
categories) and `review.csv`. The report includes suggestions, six non-selected
comparison images per batch and all remaining originals in expandable sections.
This supports checking both false positives and missed blur. No review symlinks
or image copies are created. No source or production database is written.

Label examples in review.csv as `acceptable`, `unintentional_blur`,
`intentional_softness`, `low_texture`, or `uncertain`, with notes. Include missed
blurry images, not just suggestions. Labels are evaluation data; the report does
not yet ingest them or apply a learned cutoff. Use these observations to decide
whether edge/texture, exposure or scan-profile handling warrants another
measurement experiment before adopting any severe-blur decision rule.

No production integration, merge or push is authorized.

## Subject-detection audit

The ranking/focus helper currently runs **faces only**. The initial culling
sampler ignores those regions and uses global/tile detail. People, animals and
saliency were not part of the earlier reports. Do not present them as implemented
subject-aware culling.

`subjects.swift` is a diagnostic extension of the same ImageIO/CoreGraphics
decoder. It independently runs face rectangles, full-body human rectangles,
animal recognition, attention saliency and objectness saliency at 1024 and 2048
pixels. Each request's actual revision, observations and failures are exported.
The local installed Apple SDK headers were used to verify APIs and coordinate
semantics. No new dependency or external model is used. Saliency provides boxes,
not semantic vehicle/building recognition. All observations are displayed; no
new observation-confidence threshold is applied. Out-of-frame boxes retain raw
coordinates and are clipped only for display.

```sh
xcrun swiftc -O -module-cache-path /private/tmp/photo-focus-modules \
  experiments/ranking_culling/subjects.swift -o /private/tmp/photo-subject-audit
.venv/bin/python experiments/ranking_culling/subject_audit.py \
  --helper /private/tmp/photo-subject-audit \
  --baseline-export /path/to/earlier/analysis.json \
  --output-dir /path/to/new-subject-audit photo1.jpg photo2.jpg
```

`subjects.html` contains embedded previews with individually toggleable SVG
overlays, expected subjects for the supplied ten-image evaluation set, counts,
raw observations, previous usable-face counts, and expandable 2048 comparisons.
`subjects.json` explicitly exports detector observations, image hashes, OS,
helper/source hashes and versions; no original photograph or metadata is written.
Source byte hashes, sizes and modification times are verified before publication.
Baseline export hashes must match the audited images. Decoding failures abort;
individual detector failures are visible as failures, never zero detections.

These diagnostic detectors are not integrated into the focus engine or culling
rules. The audit should guide selection and evaluation of subject regions before
requesting focus labels or claiming reliable subject-aware culling.

## Regional focus diagnostic

`region_focus.py` consumes the subject audit's detector boxes and source hashes.
The helper's `--pixels-only` mode decodes fresh native 1024/2048 sRGB previews
without repeating Vision. It does not measure the JPEG thumbnails. Measurements
reuse `quality.focus_fields`, the common Laplacian/Sobel calculation also used by
ranking and culling. Extracting this shared function preserved the existing
metric formulas and values; source-byte cache fingerprints conservatively change
when the measurement implementation file changes. Prior exports remain historical
results, but their automatic reuse checks will require fresh measurement exports.

```sh
xcrun swiftc -O -module-cache-path /private/tmp/photo-focus-modules \
  experiments/ranking_culling/subjects.swift -o /private/tmp/photo-subject-focus
.venv/bin/python experiments/ranking_culling/region_focus.py \
  --audit /path/to/subject-audit/subjects.json \
  --helper /private/tmp/photo-subject-focus \
  --output-dir /path/to/new-regional-focus-output
```

Every region is retained. Measurements are presented face → person → animal →
objectness → attention, without choosing one region and discarding co-primary
subjects. Eye landmarks are not measured in this diagnostic. A minimum 24-pixel
region side is applied independently at each input resolution; confidence scores
are recorded but no new confidence cutoff is imposed here.

Derivatives are computed on the full image before applying masks. Each sampling
mask is eroded by one pixel to avoid artificial crop-boundary responses. Raw and
sigma-1-smoothed Laplacian variance, Tenengrad, gradient-energy 90th percentile,
luminance mean and spread are recorded within each region. They are compared
with the pixels outside that region and every detected face/person/animal box,
with an additional three-pixel exclusion guard. This outside area can contain
undetected dogs/people or other subjects: it is a contextual reference, not a
verified background segmentation. Fewer than 100 sample pixels produces an
unavailable measurement, and zero reference detail produces no ratio.

`region-focus.html` retains the toggleable boxes, adds regional metric tables,
and labels boxes with their smoothed Tenengrad region/outside ratio (`T/out`).
`region-focus.json` explicitly exports complete raw/smoothed region and outside
measurements, detector observations, identities and implementation hashes. Source
content, size and modification times are checked before publication. No original
image or metadata is written. No ranking decision, severe-blur threshold, or
culling verdict is added.

Ratios describe measured texture/edge contrast as well as focus. A sharp face can
have less texture than foliage; a soft person's clothing or outline can have more
edge energy than a smooth sidewalk. Region size, background leakage and grain
also matter. The ten-photo diagnostic demonstrates both useful soft-subject
signals and counterexamples; it is not a calibrated classifier.

## Provisional subject-aware review

`subject_review.py` consumes a regional-focus export and its HTML report. It
retains all regions rather than selecting a single primary subject. A face,
person, animal or objectness region can suggest review when both smoothed
Laplacian and Tenengrad region/outside ratios are below one at both resolutions.
The same detector's region must spatially match across resolutions (intersection
over union at least .5). Attention alone cannot trigger a subject suggestion.
This is an explainable concordance hypothesis, not a learned or calibrated
focus boundary; smooth faces and textured backgrounds can still cause false
positives. No thresholds were fitted to the three user-labeled examples.

The regional engine also exports 4×4-tile Tenengrad values. Images with all six
global/maximum-tile signals in the batch's bottom 10% are added as low-detail
review samples, using conservative tie counting and a 20-image minimum. This
can catch whole-frame softness without identifiable subjects. These reference
signals use the diagnostic's 1024/2048 inputs, not the earlier 1024/512 sampler.

```sh
.venv/bin/python experiments/ranking_culling/subject_review.py \
  --focus /path/to/regional-focus/region-focus.json \
  --output-dir /path/to/new-subject-review
```

`review.html` reuses regional overlays/tables, adds a shortlist and per-image
reasons, and keeps contrary face/body/animal detail evidence visible. All images
remain available. `review-manifest.json` records the policy, triggering regions,
cross-scale ratios, global values/reference fractions, focus-export path/hash,
source hashes and categories. `review.csv` has blank assessment/notes columns.
Every severe-blur field remains false; non-selected images are unassessed, not
automatically approved. Source hashes are verified before publication.

Input selection happens before native detection, with explicit file lists when
excluding rolls. The first new-set trial includes only 00052852, 00052853 and
00052854 under Scans20240620 2; expired-film folder 00052855 is excluded.
No production integration or automatic file operations are implemented.

## User-annotated FocusTests benchmark

`benchmark.py` reads the supplied headerless four-column CSV (filename, material,
color/B&W, focus/subject notes), preserves notes verbatim, and reuses a native
subject audit. Subject details are within the notes, not a separate column. The
first sample has no labels and is excluded from agreement counts. Unknown `???`
materials remain unknown. Images and samples.csv are never written.

Run subject_audit.py on the CSV image list first, then:

```sh
.venv/bin/python experiments/ranking_culling/benchmark.py \
  --csv /path/to/FocusTests/samples.csv \
  --audit /path/to/subject-audit/subjects.json \
  --helper /private/tmp/photo-subject-focus \
  --output-dir /path/to/new-benchmark-output
```

Four fixed treatments are compared: raw, Gaussian sigma=1, Gaussian sigma=2,
and bilateral d=5/sigmaColor=15 (8-bit grayscale units)/sigmaSpace=2. Both shared
Laplacian and Tenengrad measurements, global/tile signals and detected regions
are retained at 1024 and 2048. Derivatives use original native preview pixels,
not JPEG report thumbnails. This is not adaptive grain estimation, and changing
filters changes texture/contrast as well as blur response.

The same provisional review rule is used for every treatment, with separate
material reference batches. Global tail sampling is disabled for material
batches below 20 images; subject-context review remains available. There is no
validated absolute sharp-subject override yet. No thresholds are fitted here.

Reference categories are explicit interpretations, alongside the original notes:
`focus miss across image` is a whole-image miss, `subject out of focus` a subject
miss, Polaroid softness is natural softness, blank notes are unlabeled, and other
notes contain no explicit focus miss. The three explicit misses are counted for
recall; flags on other annotations are review disagreements, not independently
proven false positives. This sample is too small and lacks independent binary
labels/held-out rolls to establish generalized accuracy.

Outputs: benchmark.html with reference notes, treatment comparison and subject
overlays; comparison.csv with per-image flags; explicit benchmark.json with
full measurements, policies' decision evidence, CSV/audit identities and source
hashes. All source image hashes, sizes/mtimes and CSV hash are verified before
publication. New dependencies and production behavior changes: none.

## Accepted working baseline

The user reviewed the raw/Gaussian1 disagreements on October 12, 2026 and
selected Gaussian sigma=1 for primary review decisions. Raw remains diagnostic;
do not combine raw-only flags into the primary shortlist. Bilateral and Gaussian2
remain benchmark alternatives. Existing subject_review.py already uses the
regional engine’s default Gaussian1 treatment. This does not validate universal
thresholds, implement a sharp-subject override, or authorize production integration.

## Unlabeled follow-up folder

The benchmark accepts `--folder /path/to/FocusTests2` instead of `--csv`,
with `--treatments raw gaussian1` to run only selected methods. Folder inputs
are shallow, symlink images are skipped, source images are read-only, and
materials remain unconfirmed. The audit must use the same ordered image list.
No source CSV is created in the image folder; review.csv is generated only
in the separate output directory. Without labels, summaries show review counts
and “Awaiting labels”, not accuracy. Global reference ranks use the selected
batch and can shift when the batch is biased toward soft images. The UI uses
“No review trigger” and “Whole-frame low-detail trigger” to avoid implying a pass.

## Subject review v2: attention-only fallback

The user authorized using attention as a focus region when no usable face,
person, animal or objectness region exists. v2 requires the same two metrics,
two resolutions and spatial matching. Attention remains an uncertain subject
heuristic, not semantic recognition. This supersedes v1’s attention exclusion.
On existing Gaussian1 measurements it adds 000097550036 in FocusTests2, and
000097550007/IMG_4915 in the first set. The baseline reports remain historical.

The 15% whole-frame counterfactual added no Gaussian1 triggers in FocusTests2.
The six reported whole-frame misses have worst tail fractions 22.5–97.5%;
raising 10 to 15 does not fix them. Gaussian2/Gaussian1 smoothing response
likewise did not distinguish these examples reliably. Neither change is adopted.
A separate candidate suppresses only broad objectness cues containing a face
with higher contextual detail at both scales. It fixes 000227710017 in this
diagnostic but is not integrated or an absolute sharp-subject guarantee.

## Edge-shape follow-up experiment

`edge_blur.py` samples Gaussian1-preprocessed grayscale edge profiles along local
Sobel normals, measuring local 10–90% transition widths, contrast and acutance.
Sampling is deterministic and bounded to 3000 strong-gradient candidates per
image, shifted toward nearby gradient maxima. The 33-pixel profile window,
contrast gate (10/255), sampling stride, censored fraction and support counts are
recorded. This is an adaptation inspired by edge-spread research, not a literal
reproduction of Marziliano or published CPBD.

The contrast-aware proxy uses width limits of five pixels for edge contrast up
to 50/255 and three otherwise, reporting the soft-edge fraction. It is not a
calibrated probability. Directional evidence compares median widths in opposing
normal-angle bins (at least 25 samples each), and can respond to scene structure
as well as motion. Whole-image/tile/subject measurements use the same sampled
edges. ROI profiles can extend beyond a box; small/low-texture regions can lack
adequate samples and must not be certified sharp.

Fixed exploratory review triggers: median width >=4px; contrast soft fraction
>=.60; or opposing-bin width ratio >=1.6 with larger width >=4.5px. A minimum of
50 edges is required globally. To favor recall, evidence at either 1024 or 2048
suggests review; agreement at both scales is recorded separately. These cutoffs
were not optimized against the real-image outputs and are not universal film
thresholds. An absolute subject override is explicitly not adopted.

```sh
.venv/bin/python experiments/ranking_culling/edge_experiment.py \
  --benchmarks /path/to/FocusTests/benchmark.json /path/to/FocusTests2/benchmark.json \
  --helper /private/tmp/photo-subject-focus \
  --output-dir /path/to/new-edge-experiment
```

Corresponding subject-audit JSON files must remain beside the benchmark folders
using the existing output names. Decode in the same environment as those audits
so native geometry matches. Outputs are report.html, results.csv and explicit
measurements.json. Existing Gaussian1+attention fallback is compared without
changing its 10% global rule. Every original hash, size and mtime is checked.
All processing remains local and original images are untouched.

The edge report separates global-only and region-augmented suggestions. A
regional probe uses detected face/person/animal/objectness boxes, or attention
only when no such region exists. A probe at one scale can add review, with
support counts exported explicitly; inadequate support does not establish
sharpness. This raises workload substantially and remains an experimental
comparison, not an adopted culling rule. Complete-miss recovery in these
development samples must not be presented as validated recall.

### Facial landmarks diagnostic

`landmarks.swift` is a separate Apple Vision revision-3 76-point face-landmark
helper using the existing native decoder at 1024/2048. Compile with `xcrun swiftc
-O .../landmarks.swift -o /private/tmp/photo-landmarks-focus`, then run:

```sh
.venv/bin/python experiments/ranking_culling/landmark_experiment.py \
  --parent /path/to/RankingExperiments \
  --helper /private/tmp/photo-landmarks-focus \
  --output-dir /path/to/new-landmark-trial
```

The diagnostic reads both prior benchmarks and the edge experiment, requires
unchanged source checksums and decode dimensions, and writes an explicit export
and embedded local HTML. Dense edge profiles are measured within padded eye,
eyebrow, nose and lip regions, without upscaling. Optional `extract` stride and
sample-count arguments preserve the earlier edge probe defaults. The trial
veto requires both eyes on every detected face at both scales: ≥20 profiles,
median width <3px, soft fraction <.4. Adjacent profiles are correlated, not
independent observations. No-face/failed/unsupported cases remain unknown.
Baseline flags and animal cases are protected. This is a counterfactual on the
proposed global-contrast combination, not an adopted change to review rules.

### Subject-patch and scale comparison

`patch_experiment.py` compares connected sharp-detail patches, fixed-size
subject regions, primary-subject size selection, and confirmation of borderline
single-scale global contrast flags on both FocusTests sets:

```sh
.venv/bin/python experiments/ranking_culling/patch_experiment.py \
  --parent /path/to/RankingExperiments \
  --helper /private/tmp/photo-subject-focus \
  --output-dir /path/to/new-patch-trial
```

The report contains yes/no review columns, an all-safeguards final suggestion,
and cached face/person/animal/objectness/attention boxes. Numeric measurements
remain in the explicit JSON export, not the review page. Each safeguard column
applies only that safeguard to the previous candidate combination; final applies
all of them. Baseline misses and no-semantic-subject objectness fallback are
protected. This is experimental and does not replace the working Gaussian1 rule.

Fixed before inspecting results: 5×5 patches per subject, at least three
4-connected sharp patches; each needs ≥20 uncensored profiles of contrast ≥.1,
median width <3px, soft fraction <.4, and ≥5 profiles in each of two normal bins.
Profiles are correlated support samples, not independent observations. Fixed
size downsamples faces to long side 128 and other regions to 256, with no
upscaling; measurement context is retained around crops. A face replaces its
enclosing body so clothing cannot rescue that blurred face. Primary selection
keeps detections with ≥25% of the largest box area within each detector kind,
retaining different kinds independently. It can still misidentify primary
subjects and may ignore a small co-primary face. All selected regions must show
sharp support at both input sizes. Rectangular boxes can contain sharp
background, and resizing may hide blur: evaluate retained known misses before
adopting any override. Sources are verified before/after; no database changes.
