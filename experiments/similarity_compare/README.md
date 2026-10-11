# Read-only similarity comparison spike

Independent experiment using existing NumPy/OpenCV, the Swift preview helper,
and explicit saved Vision reports. No production command, photo editing,
database persistence, model download, or new package dependency.

From the repository root, after compiling the helper as described in
[the Vision experiment](../apple_vision/README.md):

```sh
.venv/bin/python experiments/similarity_compare/compare.py \
  /local/path/vision-analysis.json --helper /tmp/photo-vision-spike \
  --output /local/path/new-comparison.json
.venv/bin/python -B -m unittest discover -s experiments/similarity_compare -q
.venv/bin/python experiments/similarity_compare/report.py \
  /local/path/comparison-folder --labels /local/path/known-labels.json
```

Outputs refuse existing filenames. Keep reports, input images and label exports
outside Git. Native Vision may require execution outside an agent sandbox;
normal local execution remains offline. Network-deny execution was verified
for the five-dataset benchmark. Decoder/process failures abort the experiment.

The runner verifies each source against its saved Vision SHA-256 before analysis
and again afterward. It decodes native oriented sRGB previews in batches of eight,
computes 64-bit pHash/dHash and up to 500 SIFT features, and compares every saved
pair. Original Vision pair distances are retained rather than recomputed globally.
Memory holds descriptors/hash vectors, not the entire dataset's native previews.
SIFT brute-force matching is quadratic in images and descriptor counts; timing
here does not imply suitability for very large collections.

pHash/dHash are independent OpenCV implementations. Their area interpolation and
orthonormal DCT differ from Pillow/ImageHash conventions, so hashes/thresholds
must not be interchanged across implementations. Crop-resistant or color-aware
hashes were not evaluated. The OpenCV contrib `img_hash` module is not installed;
we did not replace the current OpenCV package to obtain it.

SIFT uses mutual two-direction .75 ratio matches and 3-pixel RANSAC homography.
Its provisional candidate rule is 12 inliers, at least .5 inlier fraction, and
convex-hull coverage of at least .1 in both frames. No match is an uncertain
result, not proof that images differ. Repeated buildings, shared backgrounds,
parallax, moving subjects and softness limit geometric evidence. There is no
best-frame selection. The separate group report supports transitive grouping.

The report generator accepts explicit human labels in an external JSON list:
`dataset` (comparison filename stem), `a`/`b` (zero-based baseline image indices,
with a < b), `label` (`basically_same`, `unrelated`, or `similar_subject`), and
`source` (human assessment provenance). Only explicit labels enter evaluation;
unlabeled comparisons are never assumed negative. Current labels are sparse,
selected during prior review, and do not constitute an unbiased validation set.
The galleries let the user inspect private images locally; no model/cloud visual
review is performed.

## October 11 findings

254 scans across five reviewed sets; 7,838 pairs. All 68 production regression
tests, five experiment tests, and application Pyright strict passed. Gallery
references and full CSV pair coverage were checked. Every input hash and the
production database hash remained unchanged. Experiment Python files are not
included in the production Pyright configuration; runtime tests cover them.

On four explicitly confirmed basically-same pairs, Vision at .45 found three,
64-bit hashes at Hamming ≤10 found one each, and strict SIFT found two. Both
hashes and SIFT found the known 35561 frames 9–10 at Vision distance .557;
hashes missed 5–6 and both 17268 confirmed pairs. Strict SIFT missed both 17268
confirmed pairs. All three explicitly unrelated 72743 pairs were unflagged
by hashes/SIFT at these cutoffs but flagged by Vision.

Vision OR SIFT recovered all four labeled positives while retaining the three
Vision false positives. This is complementary value, not a general measured
accuracy claim. Seventeen strict SIFT candidates were returned, eight beyond
Vision .45; additional candidates need human labels. Hash threshold relaxation
rapidly adds candidates and sometimes reintroduces known false positives.

Recommendation: review SIFT-only candidates before choosing integration. Keep
Vision configurable near .40–.45, use SIFT as corroborating evidence or optional
extra candidates, and do not mandate hash/SIFT agreement. Whole-image hashes
have not shown broad superiority on these separately exposed film frames.
Czkawka remains a subsequent independent hash-implementation comparison if
review finds insufficient value; it has not been installed or run.

Methods reference: [ImageHash algorithms](https://github.com/JohannesBuchner/imagehash)
and [OpenCV matching/homography](https://docs.opencv.org/4.11.0/d1/de0/tutorial_py_feature_homography.html).
Full private benchmark reports/galleries are saved outside Git under the scan
root's `VisionExperiments/hash-sift-comparison/` directory.

## Edited-image grouping experiment

Generate a local gallery of connected sets from a saved comparison:

```sh
.venv/bin/python experiments/similarity_compare/group_report.py \
  /local/path/comparison.json --output /local/path/report-folder
```

The existing output directory must have no colliding report filenames. This
report uses Vision distance <.45 OR strict SIFT, ignores hashes, lists every
direct link, marks bridges, and highlights singletons and sets larger than
three. Chaining does not imply all members match directly.

The 60-image edited-color test produced 20 candidate sets: 15 pairs, four
triplets and one 11-image set, with seven singletons. The large set has 48/55
direct links and no bridges. Since every image is known to have a partner,
the singletons are retrieval failures; matched membership alone cannot prove
complete recall. One missed comparison had 99 SIFT inliers and .971 inlier
fraction, but .078 minimum coverage failed the fixed .10 criterion. These
results expose a limitation for large framing changes, not authorization to
relax thresholds or integrate into production. Private results are outside Git
under `VisionExperiments/SimilarityTests-combo045/`. Eight experiment tests
passed, and source/database checksums remained unchanged.
