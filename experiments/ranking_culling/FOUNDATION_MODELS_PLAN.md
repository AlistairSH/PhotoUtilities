# Foundation Models photo-interest experiment

Planning only, October 12, 2026. Execution is deferred until the laptop OS
upgrade and a fresh capability check. This document does not authorize
implementation, model installation, production integration or metadata writes.
The latest user request supersedes the implementation instructions in the
pasted project brief.

## Objective

Help the photographer find interesting images worth considering for editing,
whether they belong to a similarity group or appear alone. Use the same visual
criteria for both. Preserve multiple strong choices and meaningful uncertainty;
never require a single winner or a fixed distribution of recommendations.

A six-image group might contain two interesting images, two maybes and two
possible culls, but could equally contain six interesting images or six maybes.
A solo image can be interesting, maybe or worth reviewing for culling without
having another image to outperform. Being unmatched is not a quality judgment.

## Evidence and reuse

The repository is on `experiment/ranking-culling`. Existing production grouping,
focus analysis, manual review and verified ZIP archives remain the baseline.
The accepted historical batch contained 475 images, 55 groups and 322 ungrouped
images; those are historical counts, not a fresh inventory of available originals.

Existing private artifacts were located under `RankingExperiments`, including
BestPhotoSamples aesthetics, expanded-set, blind-pair, Schuhmann and rsinema
results and human-label exports. The expanded four-group evaluation and the
15-pair retest were inspected. The retest records three no-clear-preference
responses and warns that prior exposure limits interpretation. These records
support preserving ties and preferences, not treating every non-favorite as bad.

Before execution, inventory current originals, saved memberships, checksums and
label versions. Preserve human notes and original choices verbatim. Reuse cached
measurements only where provenance and source hashes match; do not repeat
similarity analysis just to create this experiment. Keep private paths, images,
labels and reports outside Git.

## Assessment design

Test a two-pass approach rather than assuming it is the final architecture:

1. **Independent interest assessment:** assess every image separately, including
   every group member and every solo, using one common prompt and schema.
2. **Group context:** compare related images for meaningful differences,
   equally strong alternatives and ties. Retain the independent assessment
   alongside the contextual recommendation so changes are visible.

Group comparison must not silently demote an interesting image because another
is preferred. Redundancy is a separate observation, not evidence of a visual
problem. If an image is both compelling and technically problematic, retain both
signals; do not make possible-cull status erase its interest highlight.

Proposed fields, without calibrated scores:

- Stable asset/image ID; existing group ID or no group.
- Interest: `interesting`, `maybe`, or `no_clear_interest`.
- Problem review: `none_observed`, `possible_problem`, or `uncertain`.
- Short observable reasons for interest and problems, recorded separately.
- Assessment uncertainty and input limitations.
- Scene: controlled primary category, a few secondary tags, or uncertain.
- Optional group-context candidates, ties and differences.
- Processing status: successful, failed, unsupported or interrupted.
- Model/API version where exposed, prompt version, settings, image transform,
  source checksum, attachment order and timing.

`none_observed` means no problem was identified in the supplied view, not a
certificate of technical quality. Failed analysis is never a neutral judgment.

The report can simplify these dimensions into **Interesting / Maybe / Review
for culling**, while displaying overlapping interest and problem badges when
needed. No-clear-interest alone must not produce a culling flag. User-confirmed
editing choices and archive selections remain separate from model suggestions.

## Common prompt draft

> Assess each supplied photograph for whether it is potentially interesting or
> worth considering for editing. Consider composition, moment, expression,
> subject presentation, lighting, visual impact and storytelling. Use the same
> criteria whether a photograph is alone or accompanied by related photographs.
> Minor technical imperfections, intentional softness, unconventional framing
> and neutral expressions need not disqualify a compelling image. Record visible
> problems separately from interest. Do not invent subject intent or unseen
> details. If the image view lacks enough detail, say so. Do not force a winner,
> quota or negative verdict. Return the supplied image identifiers and brief
> reasons grounded in visible content.

Group-pass addition: identify meaningful differences and equally promising
alternatives without assuming that lower relative preference warrants culling.
Scene-aware additions provide priorities, not formulas or compulsory conventions.
Freeze initial prompts before evaluation; record revisions as separate trials.
Human labels, prior model scores and revealing filenames are withheld from model
inputs. Stable opaque IDs provide the mapping to originals.

## After-upgrade capability gate

No Foundation Models image capability has been verified in this planning task.
The pasted brief's macOS 27, image-attachment, `fm` CLI and Python SDK claims are
investigation targets, not established dependencies. Verify official Apple
documentation and the actual installed SDK after the upgrade.

Check actual OS/build, hardware, memory, Apple Intelligence configuration,
on-device model availability and any reported reason for unavailability.
Investigate CLI, Python and native Swift options; choose the simplest supported
local path with image attachments and validated structured output. Reuse the
existing Python plus small Swift-helper architecture where practical.

Gate execution on one-image analysis, two-image comparison, ID mapping,
structured-response validation and inference with networking disabled after
required public model downloads. Check orientation and supported formats. Record
latency and memory pressure. Stop if genuine local image understanding is
unavailable; preserve the plan and report the reason. No cloud/PCC substitution
or Qwen installation is authorized by this plan.

Official references to verify at that time:

- https://developer.apple.com/documentation/foundationmodels
- https://developer.apple.com/foundation-models-framework/
- https://developer.apple.com/documentation/foundationmodels/attachment
- https://developer.apple.com/videos/play/wwdc2026/241/

## Pilot and comparison sequence

1. Select about 15–25 diverse existing groups and 30–50 true ungrouped images,
   subject to availability. Sample across folders, scenes and technical quality,
   including prior model disagreements and compelling imperfect images.
   Do not choose only previously flagged or high-scoring solos.
2. Reserve a portion of groups and solos for evaluation after prompt revisions.
   Split by related group/source sequence to avoid near-duplicate leakage.
3. Obtain blind human judgments for solos and all keep-worthy group members:
   interesting/editing candidate, maybe, keep-worthy, possible cull, uncertain.
   Prior favorite labels support shortlist recall only; they do not establish
   complete acceptable sets or culling ground truth.
4. Run the independent general prompt on every pilot image. Keep this baseline
   separate from group-context results.
5. Test whole-group comparisons where supported; use subsets of 3–4 for larger
   groups. Pairwise comparisons are a diagnostic alternative. Include a
   six-image case. Track every member through consolidation; no tournament
   elimination of images before the human can inspect them.
6. Assess the same selected group images alone, in their real group and in
   shuffled/reversed attachment order. Repeat a small fixed subset three times.
   Include all-strong, all-ordinary and mixed groups to detect forced ranking.
7. Test scene classification separately, then compare general versus scene-aware
   assessment using the same images. Begin with the brief's controlled categories
   and few context tags; allow ambiguity and avoid sensitive personal inference.
8. Only after these baselines, test supplying existing Vision focus/face evidence
   as a separate condition. Do not initially provide aesthetic scores or human
   choices. Distinguish observations from uncertain technical heuristics.

Start with one inference at a time on the stated 8 GB machine. Probe supported
image sizes, initially considering 1024 and 2048 long-edge views, never upscaling.
Preserve aspect ratio and orientation and retain the exact model-view provenance.
These sizes are test candidates, not known framework limits. Investigate whether
face/eye detail is lost; never infer fine technical quality from inadequate input.

## Evaluation

Report counts and denominators separately for groups and solos, with failures
and unjudged images explicitly accounted for:

- Group shortlist recall for recorded favorites and coverage of newly labeled
  acceptable alternatives; shortlist size and review workload.
- Solo interest precision and recall against human labels, including missed
  interesting solos. Avoid meaningless solo top-one/winner statistics.
- Culling disagreements on keep-worthy images, especially interesting images;
  missed obvious problems where human judgments exist.
- Label changes for the same image alone versus grouped, attachment-order
  sensitivity, repeat consistency and resolution sensitivity.
- Scene-label usefulness, general versus scene-aware differences, and whether
  explanations describe visible evidence accurately.
- Time per image/group, memory pressure, failures and completed coverage.

Use raw counts with uncertainty appropriate to a small subjective pilot. Do not
claim calibrated confidence or generalized accuracy. Select numerical acceptance
thresholds with the photographer before the evaluation run; they remain TBD.
The practical decision is whether useful discoveries and reduced review effort
justify mistakes, latency and explanation burden. High shortlist recall alone
is insufficient if almost every image is highlighted.

## Planned experimental report

A separate local report would have grouped comparisons, highlighted interesting
solos and access to every remaining solo. Unhighlighted images must remain
reviewable so missed interesting images can be labeled. Show short positive
interest reasons and problem reasons, ambiguity, scene labels and existing focus
warnings without cluttering ordinary images. Keep general, scene-aware and
contextual results distinguishable. Reveal historical preferences separately
from initial model judgments. Support multi-selection, ties and export of human
labels; no automatic deletion or metadata-writing controls.

## Deferred metadata work

Keep scene classification, AI recommendation and explicit workflow status as
separate concepts. Test portability using disposable copies after execution is
authorized: IPTC/XMP keywords, XMP sidecars, rating fields and Finder tags across
JPEG/HEIC/TIFF/PNG and later RAW. Verify actual Photos import/search and Photomator
round trips instead of assuming field compatibility. Recommend supported sidecars
or explicitly exported tagged copies based on those tests. Preserve existing
metadata, originals and Photos library internals; no production database changes
or permanent writes are part of the pilot.

## Deliverables and resumption

Current deliverable: this plan only. Future authorized execution would produce
capability findings, a standalone experiment, structured private results, a local
review report, performance/evaluation findings and metadata compatibility advice.
Potential code location: `experiments/ranking_culling/foundation_models/`.
Private outputs remain outside the repository. Use source-checksum checks,
collision-safe publication, explicit interrupted states and validated response
IDs; test invalid/unsupported inputs and partial failures.

Resume after the OS upgrade and an instruction to implement the experiment.
Recheck repository status and preserve existing work. Implementation, production
integration, metadata writes and any alternative backend each remain subject to
their separately authorized scope. This plan changes no CLI, grouping, focus
thresholds, archives, image metadata or existing human evaluations.
