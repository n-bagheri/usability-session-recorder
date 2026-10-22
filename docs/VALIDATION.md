# Windows acceptance tests and evidence

This upgrade was developed/tested in Linux. **No new Windows, OBS, Chrome UIA,
mixed-DPI, audio or Zoom experiment was performed by the implementation agent.**
The user's earlier recording/counts are baseline evidence only.

| Area | Implemented / automated evidence | Windows status |
|---|---|---|
| Calibration | UIA candidate selection, identity matching, source settings/transform calculations, stale/changed geometry tests | Unverified: actual Chrome UIA/provider bounds, DPI and OBS rasterization |
| Spatial QA | Saved-video extraction, known synthetic pixels/crops/letterboxing, independent five-point errors/status tests | Unverified: real five-target measurements |
| Time | Delayed/inconsistent activation, correlated replies, offsets/drift, PTS gaps/boundaries tests | Unverified: beginning/middle/end visible onsets |
| View/state analysis | Segments, unknown/admin intervals, repeat visits, two synthetic views, separate actual decoded frames | Unverified: real dynamic MapGen trials and operator annotations |
| Filtering | Window identity, overlap, focus, movement/resizing, DPI, preservation and button-pair tests | Earlier build user-reported 1022 inside/216 outside; new paths unverified |
| Reliability | Existing lifecycle/failure tests; saved-file decoding | Unverified: three consecutive real recording cycles and hook performance |
| Zoom/audio | Existing OBS audio configuration preserved | Unverified: actual remote participant capture/attribution/playback |

## Cloud checks for this revision

Linux, Python 3.12.14, FFmpeg/ffprobe 7.1.5: **76 automated tests passed**,
including real saved-video decoding, PTS cut boundaries, 84px-strip rejection,
AOI scope/overlap/zoom rules, region exports, correction/reopen/undo, unchanged raw
SHA-256 checks and recovery of corrupt derived caches. The synthetic example was
regenerated and its region image inspected; Navigation/Gallery/Editor receive
1/1/2 presses. Compilation and `git diff --check` passed. No GUI display was available
in the cloud, so Tk interactions and display scaling were not exercised.

Commands from repository root:

```sh
MPLCONFIGDIR=/tmp/recorder-matplotlib .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m compileall -q recorder tests examples
MPLCONFIGDIR=/tmp/recorder-matplotlib .venv/bin/python -m examples.synthetic_demo
git diff --check
```

## Preparation

Record Windows, OBS, Chrome and Zoom versions, monitor positions, resolutions,
DPI, capture method, FPS, OBS source/canvas/output settings and FFmpeg version in
a local QA note inside the ignored session directory. Use consenting test operators
and nonpersonal data. Keep browser zoom fixed when UIA cannot observe it.

Launch Recorder, select the actual Chrome window, connect OBS and Auto-Calibrate.
Inspect the green boundary at all edges. Confirm the OBS source indicator names
the intended source. An error/unverified result is evidence to diagnose, not a
reason to change a JSON status by hand. Test with no overlays/filters/nested scenes.

## A. Inside/outside attribution and first activation

1. Start; use a task marker or set analysis bounds later.
2. Activate Chrome with a known content click. Do not automatically discount that
   click: it may both activate Chrome and trigger the page. Note expected behavior.
3. Click three known safe MapGen content positions. Use Alt+Tab to Notepad, place
   it over Chrome and click three times in the covered region; click outside Chrome.
4. Return to MapGen and click one more known content position. Stop.
5. Review raw presses and releases. Label expected click class in Review based on
   your controlled actions. Compare counts and reasons, including the activation
   click. If exactly four page clicks were intended, expect four included presses;
   any extra activation interaction must be accounted for explicitly.
6. Export and inspect `qa.json` → classification. Record actual false positives,
   false negatives and uncertain cases. Preserve the original JSONL and confirm
   other-app clicks are still present. Do not claim perfection from simulated tests.
7. Repeat at viewport edges, with another app foreground but an uncovered Chrome
   point, popup menus/dialogs, minimized/restored Chrome and mouse dragging/capture.

**Pass:** every known trial action is explainable; no known other-app click is
included; real content interactions are not silently lost. Uncertain cases are
reported and excluded from attributed heatmaps, not relabeled to force a pass.

## B. Spatial alignment on saved video

1. Use Verify Alignment to open the separate calibration board in the selected
   Chrome window. Close duplicate Chrome windows if source association is ambiguous.
   Recalibrate/inspect after changing the selected source or window.
2. Record clicks on all five crosshair centers. Their toggled color supplies a
   visible response; no MapGen code is altered. Save the video.
3. Review: select each click, inspect the corresponding saved frame, choose Measure
   target position (ring hidden), and click the independent target center. Use raw
   crosshairs, not a generated overlay, as the reference. Record all five errors.
4. Show QA: it must show distinct evidence, coverage, one mapping ID and observed
   error. Target max error ≤5 recorded-frame pixels. If it fails, preserve evidence
   and diagnose content bounds, source identity, OBS transforms and DPI.
5. Repeat on actual MapGen with safe known landmarks near all viewport corners and
   center; document independent reference positions. A board pass does not prove
   arbitrary MapGen layouts. Repeat with black margins, a known crop and scaling.
6. Inspect each click's PNG and matching saved-frame PTS; check edge clipping is
   reported. Rotated/unsupported sources must fail calibration, not create overlays.

**Pass:** five measured points meet the documented target for that mapping/setup;
computed/inspected states alone do not pass. Use a tighter target if UI elements
require it. Record image-pixel error and video hash in the local QA notes.

## C. Repeatability / changes

Calibrate three times without changing the setup, then restart Recorder and repeat.
Compare viewport rectangles and matrices (stable window identity is reacquired).
Repeat with Chrome moved/resized, maximized before calibration, monitors to the
left/above primary, and 100%/125%/150% DPI. Inspect boundaries each time.

Change one OBS transform/crop, size, monitor or observable browser zoom during a
nonparticipant QA recording. Confirm fresh mappings or invalid states, and the
uncertain transition interval in post-session reporting. Keep browser zoom fixed
if provider monitoring is unavailable. Test the manual fallback separately; all
operators must see/confirm guides and it must invalidate on configured changes.

**Pass:** repeat measurements agree within the spatial target, significant observed
changes are tracked/invalidated, and no operator guesses arbitrary dimensions.
Changes and reversions wholly between polls are a known undetectable case.

## D. Temporal synchronization

Record distinct visible button responses near beginning, middle and end (e.g. at
5%, 50%, 95% of duration), without modifying MapGen. In Review select each raw click,
step to the FIRST response frame, then Mark visible action time. Markers or rings
added by the analysis tool are never independent timing evidence.

Inspect temporal QA: median offset, max error, drift ppm/over-session ms, coverage,
frame gap count, frame PTS and onset uncertainty. Optionally apply the explicitly
measured median offset to the derived timeline and rerun QA. Preserve both original
and corrected results in review history. Do not fit away a drift problem silently.

**Target:** at 30FPS, max observed error ≤66.7ms and estimated accumulated drift
≤33.3ms, with ≥3 independent widely spaced actions including middle coverage.
A missing/ambiguous onset or inadequate coverage is unverified/insufficient, not
pass. Compare spoken/visible actions and both voices in original video playback
separately; mouse/video timing does not establish audio latency.

## E. Dynamic views / states

Navigate Home → Editor → another view → Editor, change content without URL changes,
open/close a panel, pan/zoom/scroll and include loading states. Generate visual
suggestions, then edit named segments and boundaries against actual video. Use
separate state labels/reference frames for repeated visits and visual changes.

Set the participant interval, leave one intentional unclassified gap and confirm
Unknown is preserved. Mark only reviewed stable states stable. Correct a false
animation suggestion explicitly, without overriding true geometry/scroll changes.
Export: each view/state uses its own real frame; no Home background for Editor
clicks. Dwell equals annotated time, mouse density is not eye gaze, and per-click
context displays the actual frame/time. Re-analysis must leave raw files unchanged.

## F. Reliability / session boundaries

Run Start/Stop three times, including a cold/heavy OBS scene. OBS must receive one
StartRecord per session; Recorder waits for settled activity rather than one
immediate snapshot. During a genuine timeout, raw counts continue, a duplicate
start is blocked, Check OBS confirms without restarting, and Stop is safe. Examine
`sync.json` startup observations and error types.

After Stop verify original and copied video, decoded frames, JSONL flush and press/
release counts. Complete cannot be shown if copy/decode failed. Test hotkey conflict
registration with another global registration, disarm/disable, hold-to-repeat and
deliberate start/stop/task combinations. Confirm ordinary MapGen interaction never
triggers a shortcut in your environment. OS checks do not prove all app bindings safe.

Verify GUI responsiveness while indexing and exporting. Watch input/disk latency
with the real mouse polling rate. A slow geometry query is uncertain; no incoming
callback is intentionally filtered. OS hooks/coalescing can still limit capture.

## G. Zoom (separate acceptance)

Repeat A/B/D with an actual remote participant, using Zoom Remote Control on the
same laptop and leaving the local mouse untouched. Check hover/move, left/right
press/release, drag and scroll; compare raw logs with video. Verify both voices and
no audio feedback. Repeat at relevant DPI/monitor setups and report event losses,
classification false positives/negatives, spatial and temporal errors.

Zoom compatibility stays **UNVERIFIED** until this real procedure is completed.
A synthetic hook, a successful recording, or an OBS audio meter is not Zoom evidence.

## H. Record-first workflow, fallback and FFmpeg 9 regression

1. On the laptop, record `ffmpeg -version` and `ffprobe -version` (including the
   reported FFmpeg 9.0.2 build), OBS 32.x, Chrome and Python versions. Run the test
   suite from README, then open an existing session through Analyze a recording
   without connecting OBS. Seek beginning/middle/end, step individual frames and
   select button presses. Expected: actual frames display without any `vsync` option
   error. Compare displayed content with the original video's player.
2. In Record a session, select the actual Chrome window and Check recording setup.
   Expected: a mouse-hook readiness probe, matched OBS source and visible page-area
   preview. No five-point measurements are required before Start Recording.
3. Reproduce the Windows UIA bottom-strip failure if the provider still exposes it.
   Inspect Advanced → Calibration details: the approximately `[0,1043,1920,84]`
   rectangle must be rejected with evidence, never shown as successful detection.
   If the provider no longer reproduces it, report that fact; the synthetic rejection
   test alone is not a new real-provider measurement.
4. Decline manual selection once, then choose Mark webpage area. Keep Chrome fully
   visible; click top-left/bottom-right webpage corners, inspect all edges, redraw
   and confirm. Expected: normal recording becomes available with alignment review
   recommended. The manual result must not claim experimental verification.
5. Separately cancel selection and explicitly choose record now/align later. Verify
   the OBS preview before starting. Record, stop and inspect the original/copy,
   raw events, failed geometry/OBS evidence and synchronization observations. All
   callbacks, including outside/uncertain ones, must remain. A failed source setup
   is not a successful video test simply because raw mouse logging worked.
6. After Stop, use Open Session and Show saved files. Confirm saved locations are
   discoverable and previous session evidence has not been overwritten. Check error
   communication for wrong password, disconnected OBS and failed video finalization.

## I. Views, regions, exports and reversible correction

1. Record a consenting operator navigating two visibly different layouts, returning
   to one layout, scrolling, opening a panel and clicking outside Chrome. Note the
   controlled action sequence. Stop; conduct the rest using saved data alone.
2. Before analysis, hash `video.mkv`, `events.jsonl`, `metadata.json`, `sync.json` and
   `calibration_observations.jsonl` using PowerShell `Get-FileHash`. Retain results
   privately. If a file is absent in an older session, note its absence.
3. Open analysis without OBS. Filter presses/releases/movements/scrolls and each
   location class; select known actions and inspect frames. Verify event facts,
   inferred location and researcher AOI labels remain visibly distinct.
4. Mark view start/end using the playhead. Name Home, Editor and separate scrolled/
   panel states, leaving an intentional unknown gap. Pick a saved reference in each.
   Edit boundaries, split inside a view, merge two adjacent compatible views with
   explicit confirmation, and delete a temporary view. Reconfirm affected layouts/
   regions. Repeated visits must remain separate despite reused semantic labels.
5. On a stable reference frame, draw/name Navigation and Search rectangles. Rename,
   redraw, duplicate and delete a temporary region. Narrow a region's valid range;
   select a reference within it. Copy to another view and verify confirmation is
   required. Overlap two confirmed AOIs and verify common presses are ambiguous,
   listed as candidates, and not counted twice.
6. Open Interaction summary. Compare press/release counts and matching pairs to
   trial notes and exported raw IDs. Include a drag and a long stationary pause:
   a button pair must not claim an intentional click; silence longer than 0.25s
   must not become full hover time. Check outside/unlabeled/uncertain exclusions.
7. Toggle original image, clicks, trails, regions and density. Change opacity,
   intensity and spread. Export and open the new run folder. Compare each clean
   frame with the original recording, verify transparent PNG alpha and dimensions,
   grid sums and separate view backgrounds. Unstable/scrolling intervals must not
   receive a static overlay that falsely claims layout consistency.
8. If a session has shifted overlays and usable geometry, select two or more known
   diagonal reference presses, mark actual independent positions on their saved
   frames, draw the webpage bounds and apply within ONE view. Inspect residual and
   annotation uncertainty in Advanced. Compare on additional unused clicks. Undo
   and verify original derived mapping is restored. A reference-fit residual alone
   is not independent accuracy evidence. Other-app clicks must remain excluded;
   resized/DPI-changed states must not inherit the correction.
9. Close and reopen analysis; verify edits persist. Re-export after an edit: a new
   run and previous annotation history must exist. Rehash the raw files: every hash
   must match step 2. In a private copy of an old session, temporarily omit optional
   QA annotations and then `sync.json`: qualitative video/views/AOIs must still open,
   while missing timing disables event-to-view assignment rather than inventing it.

## J. Windows 150% display scaling and GUI acceptance

At 100%, 125% and **150%**, resize the recording and analysis windows on the laptop's
usual display and mixed-DPI secondary monitor. Check Record/Analyze/Advanced tabs,
password field, Start/Stop/Open buttons, player, playhead/timeline, view editing,
AOI drawing, scrollbars, summaries, correction references and export controls.
Open long calibration/quality evidence: dialogs must resize and scroll. Verify
selection pixels after moving the GUI between monitors. Drag the analysis pane
splitter to expose video and tables. Record any clipped/unreachable controls or
mismatches; screen-aware sizing in code is not proof that Tk scaling works.

Cloud automated results are reported separately from these laptop acceptance
results. This upgrade has not been exercised in a real Windows GUI or against OBS
32.x, FFmpeg 9 Windows binaries, actual Chrome UIA, laptop audio or Zoom Remote
Control. Existing Windows success observations apply to the earlier tested build.
