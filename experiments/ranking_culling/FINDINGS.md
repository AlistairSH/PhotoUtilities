# First 35mm ranking trial — October 11, 2026

Input: existing 100-image similarity job `c2a5d915d62f442bb3a81424ccf24a4a`,
from the supplied Scans20240620 2 batch. Reused its 13 groups (32 grouped
images, 68 unmatched), original pair evidence and source hashes. No similarity
rerun and no production database writes.

The native helper compiled locally. Its sandboxed run failed to load the local
Vision Neural Engine model; the same read-only analysis outside the sandbox
succeeded. Decode/detection failures are batch failures, never focus verdicts.

Vision returned 11 face rectangles across the batch; eight images had at least
one usable face. None of the 13 groups had comparable nonzero usable face counts
in every member. Group 4 has usable face counts 1, 0, 1. The missing detection
could itself result from blur, pose or other causes; we cannot infer which from
the detection result. Global fallback is explicitly uncertain in every group.

Raw/smoothed/scale variants chose different winners in groups 1, 2, 4 and 12.
Groups 1–4 had combined score gaps below the provisional .10 near-tie rule.
Other groups include more stable global winners, but subject-aware usefulness
has not been validated. Noise suppression sensitivity alone does not establish
that grain caused a rank change. These scans have no independently labeled
sharpness ground truth yet.

Controlled tests verified decreasing metrics with synthetic blur, inflation of
raw Laplacian by noise, reduction of noise response after smoothing, preference
for a sharp face over a sharp background, uncertain missing-face fallback,
tiny-face exclusion, and retention of grouping evidence/unmatched report images.
The existing 81 production regressions also passed. All 100 source SHA-256 hashes
matched the saved grouping run before and after analysis.

Next: review the report and record actual preferred images in review.csv,
especially groups 1, 2, 4 and 12. Group 4 is useful for evaluating the missed
face. Before choosing new thresholds or treating smoothing as grain correction,
compare user selections against raw and smoothed alternatives. Add human
rectangles or saliency only as another explicit subject-selection experiment;
do not turn uncertain global rankings into culling decisions. Polaroid and
digital batches will test whether the same relative approach remains useful.

No culling implementation, universal blur cutoff, new dependencies, production
integration, merge or push. Files remain experimental and initially uncommitted.

## OldScans trials — October 11, 2026

The user found the first rankings unhelpful and requested these two batches. The same scoring hypotheses were retained to make the comparisons interpretable. Existing completed grouping jobs were reused.

OldScans01: 241 images, 24 groups; 64 images with usable faces; face-ranked groups []; metric-disagreement groups [2, 3, 4, 6, 7, 12, 13, 14, 16, 17, 18]; 24 uncertain groups.

OldScans02: 161 images, 18 groups; 30 images with usable faces; face-ranked groups [11, 12]; metric-disagreement groups [1, 3, 4, 5, 12, 13, 14]; 17 uncertain groups.

OldScans02 group 11 selects 000344220010.jpg consistently using faces; group 12 selects 000344220014.jpg provisionally but is a near tie with metric disagreement. These are unvalidated suggestions, not demonstrated improvements in human agreement. All 402 source hashes matched their saved grouping runs before and after analysis. Embedded previews and original links were checked for both reports. No photographs or production database were modified.

## First culling review experiment — October 11, 2026

The user reported that rankings remained unhelpful: face detection was often missing and group members generally had similar focus. Work switched to culling review sampling across all 402 OldScans images, including 268 unmatched images. Shared focus exports were reused; no Vision rerun or production database writes.

The provisional conjunction of six lower-tail detail signals selected 15 manual-review suggestions: seven from OldScans01 (five ungrouped) and eight from OldScans02 (one ungrouped). Six other low-global-detail images had relatively stronger local detail and were retained outside the shortlist. Twelve non-selected comparison images span the measurement range to help detect false negatives. All 402 images remain accessible in the report and present in review.csv.

Suggestions are clustered: OldScans01 has four in folder 00022770 and three in 00022773; all eight OldScans02 suggestions are in 00034427. This could represent roll-wide softness, scan processing, scene texture or contrast. No visual ground truth has been recorded. The clustering is exposed in the report and is a reason to evaluate examples before tuning any severe-blur thresholds.

Thirteen experimental tests passed, including constant/low-texture batches, small batches, local-detail preservation, cross-scale disagreement and invalid measurements. Report verification confirmed 402 unique previews/original links and CSV rows, 15 manual-review suggestions, 12 comparison samples and zero severe-blur verdicts. Original hashes were checked before and after generation. No originals, production commands, production database or existing Git branches were changed. New culling code remains uncommitted on experiment/ranking-culling.

## New-film batch photos20251113 — October 11, 2026

The user identified old/expired film as a confound in OldScans, and supplied a new batch mixing recent 35mm and 120 scans. Existing grouping job ea405dff60e54a64b35659f53161de79 supplied the 101 image paths and original hashes (36 grouped, 65 unmatched). All images were analyzed locally with the shared focus engine. No grouping rerun or production database writes.

The unchanged review-sampling rule produced nine suggestions: four of 12 images in folder 38710 and five of 40 in 43885. Folders 38709 (12 images) and 43881 (37) produced none. Three suggestions were ungrouped. Six comparison images and all remaining photos are available for reviewing misses. No severe-blur verdict is generated.

The first pass references the entire mixed-format batch. The folder-to-format mapping has been requested; none was assumed from folder names or image counts. The report explicitly notes this limitation. No calibrated format-specific cutoff is justified without human labels. Neither shortlist membership nor better film establishes correct blur detection.

Verified 101 unique previews/original links and CSV rows, with original source hashes matching before and after analysis/report generation. Code and scoring rules were not changed for this trial; no repeated tests were needed. No originals or production database were changed, and no commit, merge or push was performed.

## Format-separated follow-up

User labels identify 38710 as 120 and the other rolls as 35mm. The explicit focus export was projected into two reference batches without repeating image analysis: 89 35mm images and 12 120 images. Existing grouping memberships were projected to new indices. Both 38709 and 38710 have near-square previews (1024×1009); 43881 and 43885 are rectangular (1024×679). The supplied labels were retained, and clarification of 38709 was requested.

Format-separated screening shortlists seven 35mm images, all in 43885. The 120 batch is below the existing 20-image minimum and receives no automatic shortlist; this is insufficient sampling evidence, not evidence of acceptable focus. All 101 originals remain available in the report and CSV. Source hashes remain unchanged. No measurement/scoring implementation changes, merges or pushes.

## Corrected format mapping

The user confirmed 38709 is also 120. The earlier supplied mapping is superseded: 38709 and 38710 are 120 (24 images); 43881 and 43885 are 35mm (77 images). Measurement exports were projected again without repeating Vision. Both reference batches now meet the 20-image screening minimum.

The unchanged screening rule gives 7 35mm suggestions and 1 120 suggestions. The corrected report retains all 101 images; preview identities, original links and CSV counts passed verification, and source hashes remain unchanged. These are review suggestions, not validated severe-blur classifications.

## Subject audit on ten supplied images — October 11, 2026

The user requested validating obvious subjects before rating focus. The audit exposed an implementation scope gap: the previous helper was face-only, and the culling sampler did not use subject measurements at all. This was explained to the user. A separate diagnostic (not adoption into culling) tested native face rectangles, full-body people, animals, attention and objectness at 1024 and 2048. Actual revisions: faces 3; all four other requests 2. All 100 detector requests completed without failures.

Results at 1024: faces in four of six photos with a main person; full-body regions in all six. Two of the four detected faces (000438810025 and 000438850008) were usable at 1024 but excluded by the existing 24-pixel minimum at 512. Animal recognition found only one of five dogs (000438850030). Detection counts were identical at 2048; increased preview resolution did not rescue misses. Earlier saved face counts matched the new 1024 run.

Region coordinates align plausibly with the supplied subjects: objectness covers the truck in 000438810018, separate camper and pickup regions in 000438810036, and silos/building in 000438850017. It also produces a separate dog-shaped region in the beach image 000438810025 despite failed semantic animal recognition. Attention regions tend to be broader and include surrounding scenery. These are qualitative checks against the user-provided pictures, not labeled bounding-box accuracy estimates.

000438810032 has a detected, usable soft face at both measurement scales yet was not shortlisted by global/tile culling. Its failure is therefore not explained by missing detection alone. Subject-conditioned focus is not yet implemented in culling. Prioritizing a person can also omit a co-primary dog; retain multiple regions rather than applying the hierarchy blindly. The audit does not justify moving on to calibrated culling: animal coverage and primary-region selection need work.

The first audit publisher refused out-of-frame observations. Vision can legitimately emit boxes partly beyond the image; the diagnostic now preserves raw coordinates and clips only displayed overlays. Sixteen experimental tests passed, including geometry scaling/clipping and explicit detector failure visibility. The report contains 20 valid embedded previews/original links and all returned regions as toggleable SVG overlays. All ten source hashes, sizes and modification times remained unchanged. No stable production modules, original images, existing branches, database, merge or push were changed.

## Face-outward regional focus diagnostic — October 11, 2026

The user authorized measuring all detected regions on the same ten supplied photos, including an out-of-focus person against a sharper background. Detection boxes were reused from the prior audit; fresh oriented ImageIO/CoreGraphics pixels were decoded at 1024 and 2048 without repeating Vision or measuring JPEG report thumbnails. Raw/smoothed regional focus uses the shared quality engine, now factored into reusable derivative fields. Existing global metric values are unchanged, covered by an exact-formula regression; source-byte reuse keys conservatively change.

All 72 detector regions are retained and ordered face, person, animal, objectness, attention. Each is compared against pixels outside that region and all detected semantic face/person/animal boxes, guarded/eroded to avoid crop edges. Outside pixels may contain undetected subjects. No eye landmarks, primary-subject winner, culling threshold or rejection rule is introduced.

000438810032: at 2048, the smoothed face/outside Tenengrad ratio is .452 and Laplacian ratio .424; body ratios .416 and .497. At 1024 the face ratios are .662 and .272. The detected subject has less measured detail than surrounding pixels at both resolutions, consistent with the visibly soft portrait but not sufficient alone for a blur verdict.

000438850030: at 2048, the animal region ratios are .554 Tenengrad and .381 Laplacian, while the broad attention zone has ratios above one. This demonstrates why attention zones can obscure a soft subject. The sharp foreground portrait 000438850015 has face ratios 5.142 Tenengrad and 6.730 Laplacian at 2048.

Counterexample: 000438850008 looks soft in the supplied image but its person and face ratios exceed one at both resolutions (2048 face Tenengrad 2.171, person 1.905). Relative edge energy is confounded by clothing, silhouettes and lower-texture surrounding pixels. Subject regions are useful, but a simple subject/background ratio cannot reliably decide focus. Region leakage, contrast, grain and missed co-subjects remain unresolved.

Twenty-one experimental tests passed, including soft subject/sharp surroundings, no mask-generated edges, unavailable empty background, tiny regions and preservation of prior metric formulas. Report validation confirmed 20 previews/original links, 72 region overlays and 20 regional tables. Original source content, size and modification times remained unchanged. All code remains uncommitted on experiment/ranking-culling; no production code/database, main/apple-vision branch, merge or push was modified.

## User evaluation of the regional diagnostic

The user confirmed 000438810032 has an out-of-focus face and 000438850030 has an out-of-focus dog. Both should be considered possible culls, not automatic rejects. 000438850008 is marginal: keeping it depends on the whole image. This supersedes treating 008 as a definite missed-cull counterexample; its measurements remain a limitation for evaluating borderline focus. The exact three labels, source hashes and qualitative notes are saved outside the repository in the report folder’s user-evaluation JSON/CSV. No thresholds were fitted to these examples.

## Scans20240620 2: three-roll subject-aware review trial

The user supplied this as the next test set and explicitly excluded expired-film roll 00052855. Selection was performed before native processing: 27 images from 00052852, 24 from 00052853, 25 from 00052854 (76 total). No images from 00052855 were decoded or included in the reports. No similarity rerun was needed; the older export supplied identity checks only.

Native subject audit completed all requests. At 1024, seven images had face regions, 13 had people, 52 objectness, 75 attention and zero animal regions. At 2048, five had faces, 11 people, 51 objectness, 75 attention and zero animals. This records detector output, not subject-recall accuracy; no human bounding-box labels are available.

A provisional subject-aware policy requires lower regional/outside detail in both smoothed metrics at both resolutions, with spatial region matching. Attention alone cannot flag review. Whole-image low-detail sampling supplements subject evidence. No threshold was fitted to the three development labels: 032 retains face/body/objectness cues, 030 animal/objectness cues, 008 none and remains unassessed rather than approved.

New-set results: 16 manual-review suggestions; 15 have subject-region cues; 1 have whole-image low-detail evidence (these sets may overlap). By folder: {'00052852': 5, '00052853': 8, '00052854': 3}. Human agreement and false positives remain unverified.

Twenty-seven experimental tests passed. Verified all 76 manifest/CSV identities, 152 embedded previews and original links, and shortlist anchors. Source content, size and modification time were verified by regional processing; publication rechecked source hashes. All images remain unmodified. Production modules/database and existing branches are unchanged; experimental code remains uncommitted, with no merge or push.

## User feedback on the three-roll review

User labels: 000528520017 definitely OOF/not sharp; 000528520025 soft; 000528520026 overall soft/bad; 000528530004 definitely OOF with blurred dog; 000528530017 people and whole image OOF; 000528520001 whole image OOF. These are six user-selected examples, not a random or complete labeled evaluation. Labels were saved in user-evaluation.json and blank review.csv fields outside the repository; any existing nonempty user fields were retained.

The rule shortlisted 520017 (face/body/objectness), 520025 (objectness), and 530004 (objectness). It missed 520026, 530017 and 520001; all three whole-frame-soft cases also failed the global lower-tail conjunction. No threshold was tuned in response.

For 520026, Laplacian is in the lowest 1.3–2.6% at both resolutions, but 1024 Tenengrad/peak tile fractions are 11.8%/18.4%, so the six-way bottom-10% rule fails. For 520001, Laplacian is lowest 1.3–2.6%, but 1024 Tenengrad is 27.6%. For 530017, the six fractions span 9.2–21.1%. Global gradients can retain broad edges despite blur; requiring every global/tile signal in the bottom tail is too restrictive on these examples. Independent whole-image blur evidence needs evaluation alongside subject-context differences; do not merely widen percentiles to fit these labels. No originals or decision rules were changed.

## FocusTests user-annotated benchmark — October 12, 2026

The user supplied 52 samples in FocusTests (initially called FocusSamples), with a headerless four-column samples.csv: filename, material, color/B&W, focus/subject notes. The notes are preserved verbatim. Materials: 33 film, 13 digital, two Polaroid, three unknown and one unannotated image. Ten are B&W. One image has no labels and is excluded from agreement counts. Three notes explicitly describe a focus miss: 000355610007, 000355610008 (whole frame) and 000438810032 (subject). Other descriptions are not definitive binary culling labels.

Fixed raw, Gaussian sigma=1, Gaussian sigma=2 and bilateral d=5/sigmaColor=15/sigmaSpace=2 treatments were evaluated with the same shared Laplacian/Tenengrad measurements and same subject/global policy at 1024/2048, holding Vision boxes fixed. All source processing is native local decoding plus existing OpenCV/NumPy. No adaptive grain model or threshold fitting. Material reference batches were separate; global tail sampling was disabled below 20 images.

Results: raw catches 3/3 explicit misses and flags 9/48 other annotated samples; Gaussian1 3/3 and 5/48; Gaussian2 2/3 and 5/48; bilateral 3/3 and 9/48. Gaussian2 misses 000355610008. Gaussian1 flags 000355610039 (harbor), IMG_0748 (night city), IMG_1258 (natural Polaroid softness), IMG_4972 (two faces) and IMG_7653 (portrait). These are disagreements needing review, not proven false positives from independently adjudicated binary labels. The fence/bokeh example 000438810012 was not flagged by any treatment.

Interpretation: sigma1 is a useful working baseline on this set, not validated universal grain handling. Bilateral filtering at these parameters did not reduce disagreement versus raw. Stronger Gaussian smoothing changes signal ranking and can lose a whole-frame miss. Relative subject detail still confounds texture, contrast and region choice, and a calibrated sharp-subject override remains absent. Only three explicit misses exist; one was a prior development case and two are adjacent frames on one roll. No holdout/generalization accuracy claim is warranted.

An initial measurement pass aborted because sandbox ImageIO decoding gave IMG_5819.jpeg heights 766/1534 versus the outside-sandbox audit’s 768/1536. Outside-sandbox decoding reproduced audit geometry exactly; the complete benchmark was rerun there with geometry verification. No geometry mismatches were ignored. No report was published from the failed pass.

Twenty-nine experimental tests passed, including background blur label interpretation and filter schema/formula behavior. Report verification checked 52 valid previews/original links, 52 comparison rows and 104 native-resolution rows for each treatment (416 total), with per-region metric tables. Images and source CSV hashes, sizes/mtime were checked during measurement/publication; hashes rechecked during QA. Originals and samples.csv were not changed. No new dependencies, production CLI/database changes, merge or push. All experimental source changes remain uncommitted on experiment/ranking-culling.

## FocusTests annotation update — October 12, 2026

The user labeled 000097550006 as film/color with notes “Dog and person, entire completely out of focus”. The benchmark now contains four explicit focus misses and no unlabeled samples. Cached native measurements and detector boxes were reused; source hashes and CSV identity were verified. Material reference ranks were recomputed with this sample added to film. Results: {"raw": {"explicit_misses": 4, "missed": 1, "other_annotated": 48, "other_flagged": 9, "caught": 3}, "gaussian1": {"explicit_misses": 4, "caught": 4, "other_annotated": 48, "other_flagged": 5}, "gaussian2": {"explicit_misses": 4, "caught": 3, "other_annotated": 48, "other_flagged": 5, "missed": 1}, "bilateral": {"explicit_misses": 4, "caught": 4, "other_annotated": 48, "other_flagged": 9}}. The previous annotation summary was preserved beside the report. No image processing, filter parameters or decision thresholds changed; only explicit whole-image label parsing was extended to this wording.

## Raw versus Gaussian1 disagreement review sheet

Five differing review flags: 000097550006 (Gaussian1 only); 000097560006, 000097560015, IMG_0647 and P6110373 (raw only). A separate sheet reuses benchmark previews, native regional measurements and evidence, shows only these treatments, preserves CSV notes and prior verbal feedback for window/architecture cases. Preference CSV included. Original benchmark, source photos and source CSV unchanged; no native rerun or threshold changes. Five previews/original links and treatment filtering verified.

## Accepted working treatment — October 12, 2026

After reviewing the raw/Gaussian1 disagreement-only sheet, the user concluded Gaussian sigma=1 is sufficient and adding raw provides little additional value. Gaussian1 is the working review baseline. Retain raw measurements for diagnostics and reproducibility, but do not OR raw-only flags into the primary shortlist. Bilateral and Gaussian2 remain comparison experiments, not primary decision signals. This accepts the filtering treatment, not a calibrated blur classifier or production integration; subject/background texture confounds and the sharp-subject override remain unresolved. Historical comparison reports are preserved unchanged.

## FocusTests2 raw/Gaussian1 review — October 12, 2026

The user supplied 40 new selected images with a heavier softness/flaw bias and requested raw/Gaussian1 results before providing feedback. No CSV was present. Both treatments were measured with the same native detections, shared metrics and unchanged decision policy at 1024/2048. Material labels remain unconfirmed; this is one unlabeled reference cohort, not a material-calibrated batch. Native detection and decoding were performed in matching outside-sandbox environments.

Review counts: {'raw': 10, 'gaussian1': 12}. Disagreements: ['000227700007.jpg', '000227700017.jpg', '000227710017.jpg', '000238470001.jpg', '000240280036.jpg', '17268 08082025 2-022.jpg']. No correctness/recall claim is made until user feedback; the relative whole-frame rule can shift as the batch composition changes. Existing known-image labels were not silently used as new ground truth.

The page contains subject overlays, both treatments, expandable region measurements and decision evidence, plus a blank 40-row feedback CSV. Clearer UI labels replace Unassessed/Whole-image evidence with No review trigger/Whole-frame low-detail trigger. Thirty experimental tests passed, including an unlabeled two-treatment report. Verified 40 previews/original links, 40 comparison/feedback rows, 80 measurement rows per treatment and source content hashes. The measurement runner also checked source sizes/mtime before publication. No original images were modified, no new dependencies or production CLI/database changes; all work remains uncommitted on experiment/ranking-culling with no merge or push.

## FocusTests2 miss investigation and v2 attention fallback

Nine user feedback cases were recorded, preserving nonempty CSV fields. Flowers 000097550036 have no semantic/objectness box; attention ratios below one in both metrics/scales can flag them. The user explicitly authorized this fallback and subject_review v2 now includes it only when other usable regions are absent. It adds two first-set review suggestions (000097550007, IMG_4915) and one second-set suggestion (flowers). All four first-set explicit misses remain flagged.

000227710017 is an objectness-only Gaussian1 false-positive candidate: its face has L ratios 2.874/2.633 and T 3.273/3.147, person ratios above one, but broad objectness ratios below one. A diagnostic, not adopted, narrow face override suppresses that overlapping objectness cue without clearing other subjects or global evidence.

Whole-frame misses 000238460007/008 have high Gaussian1 edge-energy ranks (worst tail fraction .975/.875); 000387090010 .600, 000387090012 .350, 000528530003 .325, 000528530017 .225. A 15% conjunction catches none and adds no new G1 images; raw adds 000238470001 only. Motion smear/double edges visible in supplied 000387090010 and 000238460008 demonstrate why large edge energy is not focus evidence.

A Gaussian2/Gaussian1 gradient-retention probe was measured locally on fresh pixels for all 40 inputs, preserving matching native geometry. The new whole-frame miss ratios are not consistently high (roughly .4–.7); this feature did not solve them. No threshold is adopted. Subject-only comparisons can also fail when the subject and context are both blurry; 000528530003 is additionally blocked by metric disagreement at 2048, with regional Laplacian slightly above context while T remains lower.

The nine-case analysis sheet shows user notes, original results, v2 attention fallback, candidate face override, 15% counterfactual and probe values. Baseline benchmark reports remain unchanged. Thirty-four experimental tests passed. All source hashes remained unchanged. No production integration/database, merges or pushes. Whole-frame missed-blur detection remains unresolved and is explicitly not claimed fixed.

## Accepted v2 policy settings

The user accepted attention-only fallback and explicitly retained the 10% whole-frame threshold, rejecting the 15% counterfactual as unhelpful. No rerun requested or performed. Existing code already uses 10%; the attention fallback is enabled in subject_review v2.

## Edge-shape follow-up on both sample sets — October 12, 2026

The user authorized edge width/acutance, contrast-aware and directional probes, favoring recall over some extra review flags. Both sets (52+40=92 samples) were decoded locally at matching native 1024/2048 geometry. Gaussian1 preprocessing was retained. New fixed thresholds were set before inspecting probe outputs and were not retuned afterward. Edge spread uses sampled 10–90 transitions; the contrast-aware score is only CPBD-inspired, not exact CPBD or calibrated probabilities.

Global edge width and contrast proxy recover five of six reported whole-frame misses: 000238460007/008, 000387090012, 000528530003/017. They still miss 000387090010. Its detected objectness region at 1024 gives 73 edge samples and median width 4.257, exceeding the fixed 4px threshold; at 2048 the region has only 41 samples (insufficient). Including regional probes therefore flags all six, but the final one rests on weaker single-scale evidence. Global directional checks recover no unique cases beyond width/contrast/baseline, and do not resolve the smearing case.

Workload: {"FocusTests": {"baseline": 11, "edge_width": 17, "contrast_proxy": 14, "directional": 1, "combined_global_review": 23, "combined_region_review": 29}, "FocusTests2": {"baseline": 13, "edge_width": 21, "contrast_proxy": 18, "directional": 4, "combined_global_review": 26, "combined_region_review": 31}}. The first set’s four explicit focus misses remain flagged. Extra flags include focused/intentional-DOF portraits, the fence image and both Polaroids. Absolute subject override and material handling remain unresolved; these development results are not independent recall/precision estimates.

Raw method values, tile/subject measurements and separate global/regional decisions are exported, with a six-case summary near the top of the report. No automatic culling verdict, production change or threshold adoption. Initial sampling guards were corrected for OpenCV remap size limits and featureless arrays. Thirty-eight tests passed, including synthetic defocus, directional motion, contrast scaling and insufficient flat-field evidence. Verified 92 previews/original links, 184 native-resolution records and source content hashes, sizes and mtimes. No originals changed, no merge/push; experimental changes remain uncommitted on experiment/ranking-culling.

Final regional-support regression also passed: 39 experimental tests total.

## User review of edge-probe additions

The user accepts added flags for the window marginal case 000097560006, fence 000438810012, overall-soft 000438850008 and Polaroid IMG_1257. They reject six new flags on focused subjects with blurred backgrounds: 000438850015, IMG_0705, IMG_0790, IMG_0966, 000097560020 and 000238470015. Three additional flags are surprising/disputed: 000097550035, 000355600031 and 000355610036. This refines the earlier preference for recall: some extra review is acceptable, but the sharp-subject/intentional-DOF false-positive cluster is not.

Fixed-method ablation without rerunning pixels: [{"method": "edge_width", "scope": "global", "confirmed_whole_image_misses": 5, "acceptable_added_reviews": 4, "unacceptable_false_positives": 6, "surprising_or_disputed_flags": 3}, {"method": "edge_width", "scope": "global_and_regions", "confirmed_whole_image_misses": 6, "acceptable_added_reviews": 4, "unacceptable_false_positives": 6, "surprising_or_disputed_flags": 3}, {"method": "contrast_proxy", "scope": "global", "confirmed_whole_image_misses": 5, "acceptable_added_reviews": 4, "unacceptable_false_positives": 3, "surprising_or_disputed_flags": 2}, {"method": "contrast_proxy", "scope": "global_and_regions", "confirmed_whole_image_misses": 6, "acceptable_added_reviews": 4, "unacceptable_false_positives": 6, "surprising_or_disputed_flags": 3}, {"method": "directional", "scope": "global", "confirmed_whole_image_misses": 1, "acceptable_added_reviews": 1, "unacceptable_false_positives": 0, "surprising_or_disputed_flags": 0}, {"method": "directional", "scope": "global_and_regions", "confirmed_whole_image_misses": 1, "acceptable_added_reviews": 1, "unacceptable_false_positives": 1, "surprising_or_disputed_flags": 1}]. Both global width and global contrast preserve all four acceptable added reviews; contrast-only global screening halves the six unacceptable false positives (3 versus 6), but catches only five of six whole-image misses. Regional evidence for either width or contrast recovers the sixth (000387090010) but restores all six unacceptable false positives. Global directional evidence catches just one whole-image miss and one acceptable added review. No single tested method preserves all desired recoveries while removing the unwanted portrait/DOF flags. Evaluation is on selected development feedback, not independent validation; no rule changes were adopted.

## Candidate cascade comparison

The user asked whether global contrast followed by baseline confirmation could remove false positives. On the six reviewed whole-frame misses, baseline is false for every case: requiring baseline confirmation clears all of them (0/6 retained), also clearing all four acceptable added review cases. No-trigger cannot be used as evidence of sharpness.

A counterfactual candidate union uses baseline OR global contrast, plus regional objectness contrast only when no face/person/animal detection exists. It adds ['000097560020.jpg', '000238460019.jpg', '000387090010.jpg'] beyond that union. On selected feedback: {"confirmed_whole_image_misses": {"flagged": 6, "reviewed_examples": 6}, "acceptable_added_reviews": {"flagged": 4, "reviewed_examples": 4}, "unacceptable_false_positives": {"flagged": 4, "reviewed_examples": 6}, "surprising_or_disputed_flags": {"flagged": 2, "reviewed_examples": 3}}. This keeps all six misses and four acceptable additions while reducing the six firm unwanted flags to four, versus unrestricted regional probing retaining all six. It still needs affirmative sharp-subject evidence to veto remaining intentional-DOF flags; existing contextual or edge measures do not reliably supply that evidence. No rule is adopted or image processing rerun.

## Facial landmarks — October 12, 2026

Tested all 92 original FocusTests/FocusTests2 samples at two scales with Apple
Vision face landmarks revision 3 (76 points), dense Gaussian1 edge profiles
around eyes, eyebrows, nose and lips, and a conservative sharp-eye veto.
Original hashes, sizes and mtimes were unchanged. The report is
`RankingExperiments/FacialLandmarks-both-sets-trial-01/report.html` outside Git.

Landmarks exist on 58/184 observations, totaling 68 faces. Only one observation
met the strict eye criterion, and none at both scales. The proposed combination
before and after the veto catches 6/6 reviewed whole-image misses and 4/4
acceptable added reviews, but still flags 4/6 unacceptable false positives and
2/3 disputed examples. No photo was cleared. Reusing the broader existing
4px/.6 boundaries also clears none of these new global suggestions. No working
rule changed; these selected development examples do not establish accuracy.

000438850015 returns no landmark face at either scale, despite earlier rectangle
detection. Glasses/sunglasses and broad or scale-dependent eye transitions
limit positive sharpness evidence on other portraits. OOF 000438810032 eye
medians are 7.24/9.25px at 1024, 12.52/14.87px at 2048, versus visually acceptable
IMG_0966 at 3.59/3.55 and 5.15/4.97. This offers separation in some cases without
justifying a universal cutoff. Landmarks locate geometry even on blurry faces;
they do not establish sharpness. Dense profile counts are correlated. Next
useful experiment would address feature-size/scale dependence and unobscured
facial edges; do not loosen the veto until missed-focus safeguards are tested.

Verification: Swift compiled; 41 experimental tests passed, including missing
or sparse eye support and blurry co-primary faces; sampled landmark overlays
were visually inspected. Browser file-URL navigation was blocked, so the report
is delivered as a local artifact link.

## Subject patches, subject size and scale confirmation — October 12, 2026

Ran all 92 images at two original decode sizes. Report:
`RankingExperiments/SubjectPatches-both-sets-trial-01/report.html` (outside Git).
It contains only yes/no review flags for baseline, global contrast, no-semantic
regional fallback, previous combination, each independent safeguard and the
all-safeguards final combination; cached detector boxes remain overlaid and
can be toggled. Numeric measurements and fixed parameters are retained in the
explicit JSON export for reproducibility, not displayed in the review page.

Previous combination flags 20/52 FocusTests and 26/40 FocusTests2. Native sharp
patches clear none of the four remaining reviewed unacceptable false positives.
Standardized and primary-subject variants also clear none of those four. Scale
confirmation clears IMG_0790 (only a single-scale global contrast trigger),
reducing that reviewed group from four to three while preserving all six new
whole-image misses and all four first-set explicit misses. The four acceptable
added reviews and two disputed flags remain under scale confirmation. These
are selected development-set results, not validated precision or recall.

All-safeguards final flags 18/52 and 24/40. It changes four images to No:
000438810012 (accepted marginal fence), IMG_0790 (useful false-positive removal),
000097550037 (awaiting feedback), and 000238460007 (KNOWN soft whole-image miss).
The latter is caused by standardized patches, not native patches or scale
confirmation. All-safeguards final therefore loses one of six known new misses
and is NOT recommended for adoption. Fixed-size downsampling can manufacture
sufficient narrow detail from a soft scene, exactly the risk this test needed
to expose. Primary size selection adds no additional decisions beyond
standardization on these images. Report explicitly calls out the known miss.

Working Gaussian1 rule unchanged; no automatic rejection, deletion, commit,
merge, push or production database edits. Original checksums/sizes/mtimes were
verified before/after. Swift decoding matched cached geometry. Forty-five
experimental tests passed, covering disconnected sharp noise, protected
baseline/fallback flags, blank-region uncertainty, and independent animal
primary selection. HTML contains 92 image sections and 184 measurement rows;
representative subject/saliency overlays were visually checked as static
previews. Next usable candidate is cross-scale confirmation alone; normalized
sharp-patch override requires further work rather than adoption.
