# Windows Usability Session Recorder

A standalone Python/Tkinter research recorder. **OBS Studio records all video and
audio**; this app controls OBS v5, retains global Windows mouse input, calibrates
Chrome/OBS geometry, and reviews saved video without accessing or modifying MapGen.

**Record first. Interpret later.** Collect video and all mouse evidence during the
study, then define views, label visual regions and export per-view heatmaps using
the saved recording. Independent quality measurements are available under Advanced;
they are not a prerequisite for recording or qualitative review.

This upgrade is **not yet validated on real Windows/OBS/Zoom hardware**. Computed
alignment and researcher-confirmed layouts are distinct from measured accuracy.

## Windows setup

1. Install 64-bit Python 3.11+ with Tcl/Tk, OBS Studio 28+, Google Chrome, and
   **FFmpeg + ffprobe** on PATH. Use trusted releases from python.org, obsproject.com,
   google.com/chrome, and ffmpeg.org's Windows build links. Restart Recorder after
   changing PATH. FFmpeg is used only to decode/analyze saved OBS files.
2. From the checkout in PowerShell (initial setup only):

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   .\.venv\Scripts\python.exe -m recorder
   ```

3. In OBS → Tools → WebSocket Server Settings, enable authentication on
   **localhost:4455**. Enter the password in Recorder. Passwords stay in memory;
   they are never written to configuration, research files or logs. SDK password
   logging is suppressed. Do not expose the WebSocket port publicly.
4. Set the OBS program scene to the intended Chrome **Window Capture** source.
   Enable capture cursor. Use MKV, a local writable output folder and enough disk
   space for the OBS original plus a session copy. Disable splitting, automatic
   remux, source filters, advanced recording rescale, and video sources layered
   above Chrome. Nested/grouped sources, rotation/flips and some bounds modes are
   rejected rather than approximated. See [geometry support](docs/ARCHITECTURE.md).
5. Configure OBS microphone for in-person sessions; microphone plus desktop/Zoom
   audio for remote sessions. Use headphones and test playback of both voices.
   The GUI mode labels a session; it does not change OBS's audio settings.
6. Chrome must expose a native UI Automation webpage **Document**. If auto-calibration
   reports none, check Chrome accessibility support; where appropriate close Chrome
   after saving work and launch it with `--force-renderer-accessibility`. Recorder
   does not change Chrome profiles or enable debugging. If detection fails, Recorder
   offers a screenshot-guided manual fallback in the normal recording flow. Manual
   boundaries remain unverified until independently measured.

Dependencies are the existing OBS/pynput/NumPy/Matplotlib stack plus Windows-only
`comtypes` for read-only UI Automation. Pillow, also used by Matplotlib, is declared explicitly for supported image APIs. No browser
extension, DOM injection, custom recording engine, MapGen hooks or `.bat` launcher.

## Record a session

1. **Select the MapGen Chrome window**, enter the OBS password and choose **Check
   recording setup**. Recorder checks the OBS connection and mouse hook, detects
   the webpage area, and matches the OBS Window Capture source. Inspect the boundary
   preview. If detection fails, **Mark webpage area** lets you select two corners
   on a screenshot and redraw before confirming. No five-point test is required.
2. **Start Recording.** Mouse logging starts before settled OBS confirmation.
   Startup delays remain in synchronization evidence. An uncertain start preserves
   logging; Advanced → Check OBS recording confirmation retries without sending a
   duplicate start. If alignment is unavailable, you can explicitly choose to save
   raw evidence now and reconstruct alignment later. Check the OBS preview first.
3. **Stop Recording.** Recorder waits for OBS to stop, copies its finalized original
   and checks that saved frames can be decoded. Failures are reported; successful
   saving does not imply validated alignment or audio. Do not externally start,
   stop or pause OBS during a session.
4. **Open Session** opens analysis. **Show saved files** reveals the session folder.
   The separate **Analyze a recording** tab opens older sessions without OBS.

## Analyze a recording

1. **Review events:** play/seek/step actual saved frames; open the original video for
   audio. Toggle click markers, mouse trails and regions. Filter presses, releases,
   movements, scrolling and inside/outside/uncertain classifications; select an event
   to seek to its estimated video time. Facts, inferred locations and researcher
   region labels have separate columns. Unverified timing is always disclosed.
2. **Define views:** mark a start, seek to an end and finish the view, or add/edit its
   times and labels. Choose a reference frame inside it. Split, merge adjacent
   intervals with confirmation, or delete them. Unknown gaps stay unclassified.
   Confirm a stable layout only after reviewing the whole interval; scrolling,
   panels, navigation and loading may need separate states. Repeated visits can
   reuse semantic labels but are exported separately.
3. **Label regions:** select a view/reference frame, draw a rectangle and name it.
   Edit its geometry, label, semantic ID and valid time range; duplicate or copy it
   to another view. Copies across views require confirmation. **Interaction summary**
   shows assigned presses, complete button pairs, movement samples and partial
   observed cursor seconds. These are visual Areas of Interest (AOIs), not DOM elements.
4. **Heatmaps & export:** preview movement or button-press density, adjust opacity,
   intensity and spread, then export. Each stable view uses its own actual recorded
   frame. Exports include clean PNGs, transparent layers, composite heatmaps, labeled
   regions, numbered presses, raw grids, event CSV and region JSON/CSV. Open the exports
   folder to inspect a versioned run. Unstable/unmapped states retain clean frames
   and event reports but do not receive a misleading static density overlay.
5. **Advanced Validation** contains optional spatial/timing checks, participant bounds,
   visual-change suggestions and correction of shifted click overlays. For correction,
   select at least two widely separated raw clicks in one view, mark their actual
   visible positions on saved frames, draw the webpage boundary, then apply. Both
   axes need separated references. Undo disables the correction; raw data stays intact.
   Corrections require recorded window geometry, matching identity and capture state.
   They cannot reconstruct missing event times or unknown historical input dispatch.

Annotations save automatically with history. Reopen the same session to resume.
A missing synchronization origin still permits qualitative video review, views and
regions, but no event-to-video assignment is fabricated. See [annotation and metric
rules](docs/ANALYSIS.md) for the exact saved format and counting definitions.

The participant need not interact with Recorder. Advanced provides optional
**Ctrl+Alt+Shift+F9** start/stop and **Ctrl+Alt+Shift+F10** task-boundary shortcuts.
They are disabled/unarmed by default, require explicit registration and arming,
use OS conflict checks and suppress key repeats. Change function keys if needed;
only deliberate triple-modifier combinations are accepted. OS conflict detection
cannot guarantee compatibility with every application/Chrome extension binding.
Disable shortcuts immediately if they conflict. No keyboard content is recorded.

The optional Begin/End Participant Task marker is non-destructive. Alternatively
set both bounds in Review after the test; setup/administrative events stay in the
raw dataset and are distinguished in derived reports.

## Automatic calibration: what it does and does not establish

UI Automation accepts only an unambiguous, visible, enclosing Document contained
inside the Chrome client rectangle. Conservative relative-size/edge sanity checks
reject short bottom strips (including the reported 1920×84 result), narrow or clipped
candidates. The provider is read twice and checked against monitor bounds. Rejection
retains its evidence and offers manual selection. These checks can reject unusual
legitimate browser layouts; they do not establish experimental accuracy. No fixed toolbar height or visual guess is
used. HWND/process/class and API hit-testing still govern inside/outside attribution.
A default 0.5-second monitor rechecks geometry/OBS; measurements older than 1.5s,
changed client size/DPI/monitor or failed APIs make events uncertain until refreshed.
A journal records calibration changes. Post-session analysis also marks the interval
between changed observations uncertain, rather than trusting a transform across
an undetected change between polls.

DPI and physical desktop coordinates (including negative monitor origins) are
preserved. UIA zoom values are recorded **if the provider exposes TransformPattern2**.
Otherwise zoom monitoring says unavailable: keep browser zoom fixed and mark zoom,
pan, scroll, panels and responsive changes as separate visual states. Chrome does
not always expose exact zoom through UIA. No hidden approximation is labeled exact.

OBS does not expose a Window Capture HWND through v5: association requires a unique
match from its configured window title/class/executable to the selected Windows
identity, or a unique class/executable match if the title changed. Multiple matches
are rejected. Saved-video QA is needed to prove the intended source was captured.

The manual fallback displays a captured client-area image with guides. Draw the
content rectangle and explicitly confirm it; it is invalidated on size, DPI, title
or window-mode changes. It is not the default and is never called automatically
accurate. The recording flow can explicitly allow uncalibrated raw recording; attribution
then stays uncertain and overlays are not fabricated.

An optional CDP approach was investigated: `Page.getLayoutMetrics` gives CSS viewport
metrics, but securely associating a debugging target with the selected HWND and
physical multi-monitor geometry is not guaranteed. Enabling a remote-debugging
port can expose browser data. The app neither launches a debugging browser nor
uses `Runtime.evaluate`, injects JavaScript, or modifies MapGen. Native UIA is the
implemented default; unavailable/ambiguous providers remain a real limitation.

## Review, independent verification and dynamic states

The timeline is based on **actual saved-video presentation timestamps**, not
`frame number / nominal FPS`. Frame selection works with variable frame rate and
PTS gaps. Exact extraction decodes from the beginning and caches frames; long
recordings can seek slowly. The in-app muted preview is for research review, not
guaranteed real-time playback. Use Open original video for normal audio playback.

- Set analysis start/end at the current frame. Unknown gaps remain Unknown.
- Add/edit non-overlapping segments with arbitrary **view** and **visual-state**
  labels, boundaries, reference time and a reviewed-stable checkbox. Repeated visits
  are separate segments. No hard-coded MapGen state names are assumed.
- Suggest visual transitions scans coarse grayscale differences and records browser
  title-digest changes. Suggestions have no semantic labels and may be pan/zoom,
  animations or loading. Correct them by editing segments. A false visual suggestion
  can be explicitly marked reviewed/no spatial change in the segment dialog.
- Static heatmaps require an explicitly stable state, one valid mapping and no
  unresolved visual/scroll/zoom change or clipped/unmapped samples. Different views,
  states and visits are never automatically combined. Unknown/changing states still
  have per-click saved-frame context, without borrowing another view's screenshot.
- Select a raw click to see its time, class, local coordinate, activation annotation
  and corresponding saved frame. Numbered click context and cyan trajectories use
  the actual frame/time and do not bridge missing/outside move samples.

**Spatial verification:** record five known targets near all four viewport corners
and center. Review each raw click, hide its predicted ring using Measure target
position, and click the independent visible target center. The report stores the
frame index/PTS, video SHA-256, mapping ID, predicted/observed pixels and Euclidean
error and display-selection uncertainty. A preview too small to measure within the
target cannot pass. Five distinct well-distributed actions under one mapping, maximum error
**≤5 recorded pixels**, qualify as experimentally verified *for that measured
mapping/trial*. Multiple mappings receive separate statuses; partial coverage stays partial. This is a practical 1080p registration target, not a universal
precision guarantee; small UI targets may require tighter criteria. Inspect the
raw frame, not a generated ring, to avoid circular validation. A computed or merely
inspected mapping remains distinct from measured verification. Real MapGen trials
are still required after a separate calibration-board trial.

**Temporal verification:** identify a real visible action's first response frame
for selected clicks near the beginning, middle and end. Use Mark visible action
time. Reports compare actual PTS with the original OBS-duration estimate, calculate
median offset, max error, estimated drift and onset uncertainty. At 30FPS the target
is **≤66.7ms** (two frames); drift over the session must be ≤33.3ms (one frame).
At least three distinct, widely separated references with middle coverage are
required. Apply measured median offset only with explicit confirmation; original
nanoseconds and sync data are retained. Drift is diagnostic and not automatically
"corrected". Missing measurements mean **unverified**; frame-gap uncertainty exceeding the target also prevents a pass. See [clock domains and
limitations](docs/ARCHITECTURE.md).

**Filtering QA:** Label expected click class for controlled actions. QA reports
comparisons, false positives/negatives and uncertain outcomes. Earlier Windows
observations supplied by the user (1,238 events, 1,022 inside, 216 outside, 7 included
and 1 excluded presses at 1823×914 / 144 DPI) validate aspects of the earlier build;
they do not validate this upgrade's new UIA, transform or measurement paths.

## Files, metrics and data protection

Original `video.*`, `events.jsonl`, `metadata.json` and `sync.json` remain. New
`calibration_observations.jsonl` journals live geometry. `review.json` contains
adjustable intervals, annotations and independent measurements; prior edits are
archived in `review_history/`. `review_cache/` holds decoded frames and PTS index.
`research_analysis/report.json`, `qa.json` and `events.csv` reference raw event IDs,
line numbers, nanoseconds, derived video times, classes/reasons, view/state/segment,
local and recorded-frame coordinates, mapping and frame provenance.

Each successful export has a new `research_analysis/run-<id>/` directory; the root
report points to the current run, and previous derived outputs are retained.
`analysis.json` links the new QA status while preserving any legacy alignment result.
PNG outputs include per-segment raw/smoothed density, numbered clicks and per-click
saved-frame context. Raw density grids are exported as CSV. The metric is **received
mouse events per 128×128 recorded-frame bin**, not gaze, attention or stationary dwell.
Palette intensity is normalized to each image's maximum; compare counts, not colors
across images. Optional Gaussian smoothing is sigma=1 bin and count-preserving;
raw counts always remain. The GUI exposes adjustable Gaussian spread in grid bins,
opacity and intensity; transparent overlays accompany composites. Separate partial
cursor-time outputs use only consecutive mapped callbacks within 0.25 seconds;
long event-driven silence is unknown, not stationary hover. Small click samples should use numbered clicks, not
exaggerated smoothed hotspots. View dwell means annotated interval duration, not
where the mouse rested. Movement path is a conservative sum over consecutive
same-layout move callbacks; gaps/outside events are not bridged.

All global mouse callbacks, including outside/uncertain events and button releases,
are retained. Complete press/release pairs and unmatched events are reported
separately. A possible first activation click is annotated from prior observed
focus, never discarded merely for lacking earlier foreground focus. Windows APIs
sample state after callbacks; they cannot prove historical dispatch or distinguish
all page popups/same-title tab changes. PTS gaps can reflect dropped frames or VFR;
no automatic cause is inferred. OS-level input coalescing and hook/disk performance
must also be checked on the actual laptop.

Old sessions can be opened with their finalized video, metadata and raw events.
A missing time origin disables timed mouse assignment but keeps qualitative review.
If metadata omits the video filename, a single unambiguous `video.*` is accepted.
Corrupt derived PTS/PNG caches are rebuilt; originals are never repaired in place. Legacy
manual `frame_mapping.json` is supported when dimensions match; without one, old
inside/outside data is retained but frame overlay stays unavailable. Existing
`python -m recorder.tools SESSION` and legacy heatmap APIs remain for compatibility;
new research exports/QA, rather than layout-only aggregates, are the review workflow.

Keep sessions in ignored `sessions/` or an external private folder. Recordings,
JSONL, media, credentials and `.env` are ignored. Raw titles are chooser labels only;
recorded title digests are change signals. Do not commit personal screenshots,
URLs, recordings, passwords or exported research data. Review `git status`.

## Tests, synthetic example and Windows evidence

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m examples.synthetic_demo
```

The synthetic demo creates a mock Home/Editor session and overlays under
`sessions/synthetic-demo/`, using locally generated pictures and a synthetic MKV.
[Example outputs](examples/README.md) are explicitly synthetic, not MapGen/Windows
accuracy evidence. Saved-video integration tests exercise real FFmpeg decoding,
PTS selection, frame pixels, per-state separation, AOI assignment, correction/undo
and SHA-256 preservation of video, mouse, metadata, sync and calibration journal.
The decoder no longer uses the removed `-vsync` option; actual FFmpeg 9 Windows
execution remains a manual acceptance item.

See [Windows acceptance tests and evidence matrix](docs/VALIDATION.md) for the
required inside/outside, five-target spatial, repeatability, temporal, dynamic-view,
start/stop and Zoom procedures. Real Windows/OBS/UIA/DPI/Zoom measurements for this
upgrade remain outstanding. No test in Linux can establish that compatibility.
