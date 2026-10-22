# Measurement architecture and supported geometry

The existing `Session` engine, OBS audio/video recording, raw filenames, monotonic
clock and press/release capture are retained. Recording, saved-session analysis and
advanced diagnostics have separate workspaces; the recording engine was not replaced.

| Module | Responsibility |
|---|---|
| `windows.py`, `targeting.py` | DPI-aware Windows identities, geometry, real hit testing/occlusion and reproducible three-way classification |
| `viewport.py` | Read-only UI Automation Document bounds; no DOM text or MapGen instrumentation |
| `obs_geometry.py`, `capture.py` | Unique OBS source association, supported transform model, freshness monitor and journal |
| `obs.py`, `session.py` | Authenticated serialized/correlated v5 requests, settled activation, safe uncertain states, settled stop, stable-file copy and decode finalization |
| `media.py` | Saved-video SHA-256, ffprobe PTS index and exact-index FFmpeg frame decoding |
| `review.py`, `qa.py` | Non-destructive segments/task interval, click pairing, independent spatial and temporal evidence |
| `research.py` | Contextual per-click images, stable-state overlays, view metrics, provenance CSV/JSON, nonsemantic visual suggestions |
| `annotations.py`, `regions.py` | Version-2 visual AOIs, view edits, explicit assignment/overlap rules and conservative interaction summaries |
| `corrections.py` | View-, time- and geometry-scoped researcher registration; raw evidence retained |
| `heatmaps.py` | Adjustable count/partial-time densities, transparent layers and numerical grids |
| `gui.py`, `workspace_ui.py`, `ui_helpers.py` | Separate recording/analysis workflows, visual timeline/AOI editing and scrollable diagnostics |
| `review_ui.py`, `hotkeys.py` | Reused async saved-video player/optional measurements and conflict-checked Windows shortcuts |

## Spatial coordinates

1. Python hook callbacks receive physical desktop X/Y after per-monitor-v2 process
   DPI initialization. Windows with negative monitor coordinates are supported.
2. UIA provides a measured Document rectangle in the same physical space. Local
   viewport coordinates are desktop minus this rectangle's top-left.
3. OBS Window Capture input settings are matched against actual Windows identities.
   A client capture must match measured client dimensions. An outer-window capture
   must match a unique measured DWM extended-frame or window rectangle in dimensions
   and origin. Otherwise the source-to-desktop relationship is invalid.
4. Crop and item scaling/position/alignment convert viewport pixels to base canvas.
   NONE, SCALE_INNER and STRETCH bounds are implemented. Inner bounds alignment
   accounts for letterboxing. Canvas-to-output scaling produces recorded-frame
   coordinates, checked against actual saved video dimensions.
5. Negative scale/flips, rotation, nested/groups, crop-to-bounds, unsupported bounds,
   custom recording output/rescale, enabled filters and extra video sources above
   the target are rejected. Source/canvas clipping is excluded/reported per event.

The formula was checked against OBS's libobs scene transform implementation
(`obsproject/obs-studio`, `libobs/obs-scene.c`, `calculate_bounds_data` and
`update_item_transform`). OBS can round alignment terms to integers and rasterize
subpixel coordinates; independently measured saved-frame error remains authoritative.
No formula, API success, UIA rectangle or source name alone establishes accuracy.

UIA provider coverage and exact Chrome Document bounds require Windows acceptance
tests. No fixed browser-bar height is used. `TransformPattern2` zoom reporting is
optional; unsupported zoom is explicitly marked unobservable. The fallback uses a
confirmed visual rectangle and invalidates on changes rather than guessing.

Live observations are non-atomic and polled every 0.5s by default. They must be
fresh (≤1.5s and measured within 1.5s) and match immediate window geometry. Analysis
uses the journal to conservatively mark intervals around changed observations
uncertain. A change that occurs and reverts wholly between polls cannot be detected;
keep OBS transforms fixed during participant trials, inspect video and repeat QA.

## Clock domains

- Raw input `monotonic_ns` is Python `perf_counter_ns` at callback entry; it is not
  Windows hardware-event time. Delayed geometry queries over 100ms become uncertain.
- OBS `outputDuration` is an OBS recording clock in milliseconds. A bracketed
  request midpoint estimates its offset from the Python clock. Half RTT captures
  transport uncertainty only. Two settled status polls prevent the previous
  immediate-start false failure. Request IDs protect against stale responses.
- Encoded media uses presentation timestamps. The first decoded video PTS becomes
  saved-video zero; frame count divided by FPS is never used for event association.
  Encoder/audio latency, dropped frames, hook delay, VFR and OBS clock behavior can
  still shift visible onset relative to a duration-based estimate.
- Derived event time is `(event_ns - origin_ns)/1e9 + manual_correction_ms/1000`, plus
  an explicitly accepted review-only offset (optional drift field supported in the
  model). Original input and OBS samples are not rewritten. Measured drift is
  reported; the GUI does not automatically fit away drift or guarantee alignment.

Three independently visible actions at beginning/middle/end are the minimum for
measured temporal QA, spanning ≥50% of the video and covering the first/last 20%.
Max measured error must meet the two-frame target and drift the one-frame target.
Onset uncertainty (normally one frame) is retained. A "measured pass" describes
those observations only, not every video frame or every future participant.

## Experimental statuses

Spatial statuses distinguish computed, visually inspected, insufficient coverage,
experimentally verified and failed. Each measurement cites a raw event, decoded
frame, full video SHA-256 and mapping ID. Verification requires five distinct
points covering corners and center under one mapping and error ≤5 pixels.

Temporal statuses distinguish unverified, insufficient measurements, measured pass
and measured fail. Researcher-annotated view labels are not automatically verified
semantics. Unknown intervals and invalid mappings remain data, not fabricated labels.

Generated overlays carry QA references; numerical projection is never counted as
an independent observation. A calibration board is a separate static page owned
by this recorder, not injected into MapGen. Its results must not be substituted
for checking the real application's viewport and content states.

Each export writes to a new versioned analysis run. Only the root derived report/QA
pointers are updated; raw recordings and earlier export runs are retained.

See [analysis schema and rules](ANALYSIS.md) for version-1 compatibility, corrections,
region metrics and export provenance. No additional runtime dependency is introduced.
