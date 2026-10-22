# Saved-session analysis and annotation rules

Analysis uses only saved evidence. MapGen is not accessed or modified. The recorder's
existing OBS session engine, raw physical desktop coordinates and monotonic time
model are retained. No participant needs to repeat a task to label saved views.

## Stored evidence and editable interpretation

| File | Meaning |
|---|---|
| `video.*` | Copied original OBS recording; never re-encoded or edited by analysis |
| `events.jsonl` | Original callbacks, physical X/Y, nanoseconds, press/release, original classification and available window/source observations |
| `metadata.json`, `sync.json` | Original capture conditions and clock observations |
| `calibration_observations.jsonl` | Original changing/failed viewport and OBS geometry evidence |
| `review_cache/` | Derived PTS index and decoded frames; safe to regenerate |
| `review.json` | Researcher interpretation, schema version 2 |
| `review_history/` | Previous saved annotation versions |
| `review_suggestions.json` | Derived coarse visual changes; suggestions, not semantic truth |
| `research_analysis/run-*/` | Versioned export images, numerical grids, reports and QA |

Version-1 review files load with additive defaults, preserving existing intervals,
labels, measurements and unknown fields. They are not rewritten simply by opening
them. Saving archives the previous review before atomically replacing it. There is
no automatic rollback UI; an archived review can be restored as `review.json` with
the workspace closed. Earlier analysis runs are retained.

Schema 2 retains version-1 segments, `analysis_interval`, measurements, optional
derived time correction and inspected mapping IDs, adding:

- `aois`: unique `id`, reusable `semantic_id`, label, `segment_id`, `[x,y,width,height]`
  rectangle in `recorded_frame_pixels`, half-open `valid_interval`, original saved
  `reference_frame` (index, PTS, size, video SHA-256), `layout_confirmed`, priority,
  creation/edit timestamps and researcher provenance.
- `aoi_overlap_policy`: defaults to `ambiguous`. Overlapping eligible regions leave
  the event unassigned and list candidates. An explicitly configured `priority`
  policy chooses the smallest integer priority, breaking ties by stable ID. The GUI
  edits priority values; selecting the alternative global policy currently requires
  editing `review.json` with the workspace closed. No event is counted twice.
- `mapping_corrections`: optional researcher-fitted axis-aligned registrations with
  reference anchors, desktop-to-frame matrix, drawn webpage bounds, view/time scope,
  recorded geometry fingerprint, video fingerprint, residual and annotation
  uncertainty. Fitted references are calibration inputs, not independent proof.
- `heatmap_settings`: opacity, intensity and Gaussian smoothing sigma in grid bins.

AOIs copied across views require renewed layout confirmation. Splitting clips time
ranges and disables an AOI when its reference is no longer in its interval. Merging
requires adjacent intervals and explicit compatibility confirmation; it resets
layout confidence. Structural edits disable applicable corrections for re-approval.
Reused view labels/semantic IDs prepare for future comparisons but never merge
pixel data across sessions automatically.

## Assignment and counts

An event is assigned only when its estimated video time is in the participant
interval, a named view and the AOI's valid interval; the target classification is
inside; its projection is unclipped; and the mapped point lies inside the rectangle.
Rectangle right/bottom edges and time interval ends are exclusive. A confirmed stable
layout, matching video reference and valid mapping are required. Scroll events,
changing mappings, observed zoom changes and unresolved visual suggestions block static region metrics;
define separate states around changes. Missing timing prevents assignments without
preventing qualitative video review. Unobservable layout changes still require
researcher inspection of the saved video.

`region-events.csv` includes every mouse event's assignment or explicit exclusion
reason, candidates and mapped position. `region-summary.csv` and `regions.json`
include:

- Button presses and releases counted separately at their mapped positions.
- Complete matching button down/up pairs counted by the assigned press, even if
  release occurs elsewhere. A pair can represent dragging; neither pairs nor raw
  presses establish the number of intentional clicks.
- Received movement callback counts, first event time and press sequence relative
  to the view start. Event IDs link these summaries to raw lines.
- **Partial observed cursor time:** only consecutive raw events assigned to the same
  AOI with positive gaps no longer than 0.25 seconds contribute. Longer silence is
  unknown. This is a bounded estimate, not a complete stationary hover/dwell measure.

Reports retain original classifications separately from current policy replay and
researcher corrections. A correction retains recorded identity, historical hit-test,
occlusion and delayed-query checks. It does not make a known other-app click inside.
It applies only within its time range and identical recorded window/capture geometry.
An uncertainty band near corrected boundaries remains uncertain. Without window
observations, identifiable reference clicks and usable timing, reliable retrospective
mapping cannot be reconstructed. Correction/undo never rewrites the raw dataset.

## Heatmap calculation and exports

Each confirmed stable segment uses its own decoded representative frame whose PTS
lies inside that interval. A segment with no saved frame needs longer boundaries;
analysis never borrows an image from across the cut. Frames retain the saved
video's actual dimensions. Unknown layouts, changing mappings, scroll/detected zoom
changes, unresolved visual suggestions or unmapped/clipped inside events prevent a
static heatmap; clean screenshots and event reports remain available.

Movement density is received movement events per cell of a 128×128 grid covering
the full recorded frame. Button density uses press positions. Raw grids preserve
counts; adjustable Gaussian smoothing preserves the grid's total. Intensity scales
color/alpha relative to that image's maximum; opacity scales the transparent layer.
Compare numerical counts, not colors between different views or participants.
Separate partial-cursor-time grids weight bounded consecutive same-mapping callback
intervals in seconds. They do not fill long gaps or establish gaze/attention.

Each eligible segment exports `*-original.png`, `*-move-density.png`,
`*-click-density.png`, corresponding `*-transparent.png` layers and raw `.csv` grids,
plus optional smoothed-count grids, partial-cursor-time images and numbered presses.
Region outlines use saved frames within their own valid intervals. Each AOI also
exports its clean and labeled reference image. `events.csv`, `region-events.csv`,
`region-summary.csv`, `regions.json`, `report.json` and `qa.json` preserve numerical
results, frame provenance, reasons and unverified statuses. Root report/QA files
point to the latest run; earlier runs remain. No cross-participant aggregation is
implemented. Compatible layouts or validated normalization would be required.

FFmpeg only decodes saved recordings; OBS remains the sole audio/video recording
engine. Exact-index frame decoding uses `select` and `-frames:v 1`, without `-vsync`.
Long videos can seek slowly because decoding starts from the beginning. Frame gaps
may indicate VFR or dropped frames; their cause is not inferred automatically.
