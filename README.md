# Windows Usability Session Recorder

Standalone Python/Tk desktop controller for OBS Studio (obs-websocket v5).
It captures Windows global mouse input via pynput, without reading or modifying
MapGen or any other application's source. OBS records all video and audio.

## Windows setup

1. On Windows 10/11, install 64-bit Python 3.11+ from python.org, including Tcl/Tk, and OBS Studio
   28+ from obsproject.com. Use a local interactive Windows desktop.
2. In PowerShell, from this checkout:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   .\.venv\Scripts\python.exe -m recorder
   ```

3. In OBS: Tools → WebSocket Server Settings → enable server on port **4455**,
   enable authentication, and copy its password into the GUI. The app connects to
   localhost only. Passwords stay in memory, never in session files. Optional
   `OBS_WEBSOCKET_PASSWORD` can supply it from the process environment. Do not
   expose this port publicly.
4. Create an OBS scene with Display Capture or Window Capture for Chrome/MapGen.
   Enable capture cursor. Check the preview, scaling, cropping, and output size.
   Prefer MKV recording to protect against interrupted recordings. Use a local,
   writable output directory with enough space for both the OBS original and the
   session copy. Disable automatic output splitting and automatic remux for the
   MVP. Do not pause recordings or start/stop them outside this app.
5. Configure audio in OBS, not this recorder. In-person: microphone enabled.
   Zoom: microphone plus desktop/Zoom audio enabled, with headphones to avoid
   feedback. Confirm the meters and make a short playback test for both speakers.
   The GUI mode selector labels metadata; it does **not** change OBS audio sources.

## Session workflow

- Get participant consent for video, cursor activity, and conversation recording.
  Close personal windows and notifications. All desktop mouse input is logged,
  including input outside MapGen; no keyboard input or window titles are logged.
- Connect to OBS. Set the local sessions folder (default `sessions/`, Git ignored).
- Click **Refresh Chrome windows**, select the MapGen Chrome window (title is a
  chooser label; HWND, process ID, process creation time and class identify it).
  Select the same window in OBS Window Capture. No MapGen repository access occurs.
- Click **Pick content corners**. Recorder minimizes. Within 30 seconds click the
  top-left content pixel and then the bottom-right content pixel, inclusive. Exclude
  tabs, address/bookmarks bars, borders, and any Chrome side panel. These clicks are
  delivered to Chrome, so use a safe page state. Both corners must hit the selected
  unobscured window, with stable geometry. Calibration is required for each session
  configuration; raw browser titles are not written into recordings.
- The legacy desktop rectangle is used only for legacy/unselected-session analysis,
  not for new MapGen-only heatmaps. Physical pixels are used throughout; monitors
  left/above primary can have negative coordinates. Do not enter DPI-logical pixels.
- Movement and ordinary resizing are tracked per event. Insets are calibrated in
  physical pixels at a known DPI and scaled at DPI changes. Different content sizes
  and DPI values get separate heatmaps, not one stretched aggregate. Calibrate in
  the intended normal/maximized state: switching that state mid-session is uncertain
  until a new session is calibrated, since Chrome's toolbar/border height can change.
  Do not change tab, browser zoom, side panels, bookmarks-bar visibility, fullscreen,
  OBS scene/transform, or browser UI configuration during an analysis trial.
- Start Session. The input hook begins before requesting OBS StartRecord, so
  events during startup can have negative estimated video times. Status confirms
  OBS active/unpaused in two successive status polls before reporting Recording.
  Input capture continues throughout startup. Do a short input/audio check.
- Use Sync Marker near the beginning and end. See synchronization below.
- Stop Session. Wait for OBS acknowledgement and video copying. The OBS original
  is retained. Generate Heatmaps and select the completed session folder.
- On errors, read the dialog. If start or stop timed out, inspect OBS and retry Stop
  before closing, or use **Check OBS** to confirm an uncertain start without sending
  StartRecord again. Recording may still be active. Metadata and raw events are
  flushed during capture; interrupted sessions may need manual video recovery
  from OBS's recording folder. If copying fails, retry Stop with sufficient disk
  space; the saved original output path is retained. Never start another recording
  while recovering an uncertain session.

## Files and synchronization

Each unique session folder contains:

- `video.mkv` (or OBS's selected extension): copied after recording stops.
- `events.jsonl`: monotonic nanoseconds, mouse type, physical X/Y, button/press,
  scroll deltas, desktop/foreground/target geometry, per-event target observation,
  content-local/normalized coordinates and classification/reason. All received
  move/click/scroll callbacks are kept, including outside and uncertain events;
  there is no target filter or movement throttle at capture. OS input may itself
  be coalesced; these are callback timestamps, not hardware timestamps.
- `metadata.json`: UTC creation time, mode, capture rectangle, OBS request/response
  timestamps, target identity/content calibration, output path, state, counts and input errors.
- `sync.json`: OBS duration samples, origin estimate, half request round-trip
  times, marker times, startup status observations, and a manually measured correction.
- `mapgen_move_<width>x<height>-dpi<N>.png` and
  `mapgen_click_<width>x<height>-dpi<N>.png`: MapGen-only event counts, one pair
  per content size/DPI. Axes are content-local physical pixels with top-left origin.
  Clicks count presses, not releases; moves are event density, **not dwell time**.
- `analysis.json`: included/excluded/uncertain counts for all mouse events and for
  click presses separately, reasons, per-layout totals/files, and alignment status.
- `frame_mapping.json`, `reference-*.png`, `mapgen_click_overlay.png`: optional
  explicit frame calibration, copied reference frame, and annotated clicks. These
  stay within the ignored session folder. No overlay is produced if uncalibrated.

Older sessions lacking target observations still generate the original desktop
heatmaps; they cannot be retroactively classified as MapGen-only. A recorded
foreground window or title alone is insufficient evidence.

## What inside/outside/uncertain means

`inside` means the selected handle/process/class identity matches, the target is
visible, geometry is stable during observation, the point is in the calibrated
content rectangle, and Windows hit-testing resolves to that window's root.
Another app being foreground does not automatically exclude a hover over visible
MapGen. A point outside content (including Chrome controls), another root at the
point, or mouse capture by another window is `outside`. Failed APIs, a closed or
replaced target, missing hit tests, changed page-title digest, changed window mode,
or moving geometry during the query are `uncertain`. Z-order bounds are also
checked: potentially covering transparent/irregular windows which hit-testing
might ignore cause `uncertain`, rather than an assumed inside event.

Each event saves its observation, query interval, policy version and reason.
Analysis replays the classifier using metadata calibration and saved observations;
it does not delete or rewrite raw logs. Only `inside` events enter MapGen heatmaps.
The identity includes HWND, PID, process start time and window class, rather than
relying on a title. Titles appear in the GUI only; their SHA-256 digest is saved
as a conservative change detector.

Windows APIs identify windows, not browser URLs or DOM elements. Content calibration
is the user's confirmation of the MapGen viewport. A different page with the same
title, an in-window Chrome side panel, responsive UI changes, or browser zoom cannot
be reliably detected by this OS-only MVP. Keep the selected tab/UI configuration
fixed and validate using the four-click procedure below. Same-size layouts across
workflow steps are spatially aggregated, not semantically aligned. Window geometry
and hit-testing are observations after the hook callback, not an atomic historical
OS dispatch record; query intervals are retained for auditing. No Windows or Zoom
compatibility claim is based on simulated tests.

## Click overlay: explicit OBS/frame calibration

1. Complete a controlled session, click **Generate Heatmaps**, and select its folder.
   Read `analysis.json` for layouts and included/excluded/uncertain click counts.
   Alignment initially says **unverified**, which is expected.
2. Export a PNG at the original resolution from the session's OBS video using your
   video player, or save a representative OBS output screenshot at the same
   resolution. Use the same window layout, page state and OBS transform as the
   clicks being checked. Do not use a rescaled image from a document or chat.
3. Click **Align Frame**, select the session, enter the exact layout key listed
   (e.g. `1280x720-dpi96`), and select that PNG.
4. Enter the visible **source crop** in MapGen-local physical pixels:
   `left,top,width,height`. Full uncropped content is `0,0,W,H` from `analysis.json`.
   If OBS removed 100 pixels from the left, start source X at 100 and reduce width.
   Chrome toolbar/window borders are already excluded from MapGen-local space.
5. Measure and enter the corresponding content bounds **in the PNG** as
   `left,top,width,height`. Exclude black bars and any surrounding Chrome toolbar.
   This explicitly accounts for OBS source cropping, scaling and letterboxing;
   nonuniform axis scaling is supported, rotation/perspective are not.
6. Open `mapgen_click_overlay.png`. Red numbered rings must match the known click
   locations. It preserves the exact reference image resolution. Only clicks in
   the selected layout and visible source crop are plotted; cropped-click counts
   are reported. Other layouts require their own frame calibration; align them
   separately, retaining copies of prior validation outputs if needed.
7. Calibration records are saved in `frame_mapping.json` and copied to the report.
   The report says `calibrated_mapping_applied_visual_verification_required` until
   you verify the image yourself; applying a transform is not proof of alignment.
   If you cannot measure the mapping confidently, leave it unverified. Never infer
   it from output size alone. Changes to OBS transforms mid-session need separate
   sessions/analysis; this MVP cannot reconstruct those changes.

## OBS startup fix and diagnostics

The original code called `StartRecord`, immediately performed one `GetRecordStatus`,
and raised "inactive or paused" if that snapshot was not active/unpaused. A successful
start request is not reliable evidence that the next status snapshot has settled.
The application was already capturing input and OBS had received the start request,
which explains why Stop could still stop/save the recording after that exception.
This single-snapshot failure path is reproduced by simulated delayed/inconsistent
status responses. We do not have the failing laptop's OBS trace, so the exact
OBS-side transition timing/version behavior remains to be measured there.

The fix sends StartRecord once, then polls for two consecutive active/unpaused
responses with valid nondecreasing duration. Polling retries for 10 seconds at
150 ms intervals; one in-flight socket request can additionally take up to the
configured 10-second request timeout. Request/response times, flags, durations and
request-error types go to `sync.json` → `startup_observations`. An uncertain start
keeps the input hook/file open and blocks duplicate StartRecord. **Check OBS**
retries confirmation only. **Stop Session** sends StopRecord without depending on
one potentially stale inactive status, and keeps capturing if stop fails. After a
stop acknowledgement, video copy can be retried without sending another StopRecord.
If OBS was stopped externally or a stop response was lost, OBS may reject a retry;
retain the session and recover the video manually rather than silently claim success.

The shared clock is `time.perf_counter_ns()`. A status request brackets OBS's
`outputDuration`; midpoint minus duration estimates recording zero. The lowest
half-RTT sample is selected. This accounts for startup delay better than assuming
StartRecord request time equals video zero. Half RTT measures transport uncertainty
only: OBS scheduling, duration granularity, encoder/scene/audio latency and Tk
rendering are additional unknowns. No frame-accurate guarantee is made.

To verify on the actual laptop:

1. Capture the sync popup in OBS (Display Capture, or temporarily arrange the OBS
   scene to include it). A popup outside a Chrome Window Capture will not appear.
2. Press Sync Marker several times at the start and end; optionally say its number
   aloud to compare audio as well. Markers are logged before the popup is drawn.
3. After stopping, run:

   ```powershell
   .\.venv\Scripts\python.exe -m recorder.tools sessions\YOUR_SESSION
   ```

   This prints marker video-time estimates and sample-origin spread and writes
   `timeline.jsonl` with estimated video seconds, preserving raw events.
4. Frame-step video in a player to find each visible popup onset. Compare actual
   onset time with the report. Record offsets and variation; the popup's rendering
   delay is included. A click visible in the captured application provides an
   additional check closer to the mouse interaction. Enter **actual minus
   estimated time in milliseconds** into the GUI's correction field for the current
   session, Save correction, and rerun the report. For older sessions, edit only
   `manual_correction_ms` in their `sync.json`. Compare multiple markers to detect
   drift: a single offset cannot fix drift or pauses. Preserve measured residual
   errors in a local session note. Audio synchronization must also be checked by
   playback; it is governed by OBS's audio configuration.

## Zoom remote-control diagnostic (must validate on Windows)

Global hooks may capture Zoom-injected events, but this depends on Zoom version,
Windows permissions and the remote-control path. Compatibility is **unverified**.

1. First record a local baseline: move in a recognizable pattern, left/right click,
   drag, and scroll both directions; observe increasing GUI counts and review video.
2. Start a separate session labeled `zoom`. Share the intended screen/window and
   grant a second person remote control. Keep the local mouse untouched.
3. Ask them to repeat the same pattern, clicks, drag, and scrolls. Observe counts,
   inspect JSONL event types/positions/press-release pairs, and compare with video.
   The hook does not attribute events to a person; label controlled trials clearly.
4. Check secondary monitors, negative coordinates, mixed DPI, foreground changes,
   and any elevation mismatch. Avoid running tested applications elevated unless
   necessary. If video shows movement but events are absent, the current Zoom/input
   configuration is unsupported; do not use these logs for heatmap conclusions.
5. Play back microphone and remote participant speech. Confirm sync markers at
   both ends and document measured timing error before collecting real sessions.

## Detailed Windows acceptance checklist

Run this first in person, with synthetic/nonpersonal content, then repeat through
Zoom with a second person. The automated tests below do not replace this checklist.

1. Update the checkout and dependencies in PowerShell:

   ```powershell
   git pull --ff-only origin main
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   .\.venv\Scripts\python.exe -m recorder
   ```

2. Open MapGen in Chrome and another application (e.g. Notepad). Choose the matching
   Chrome window in OBS Window Capture. Refresh/select it in Recorder, pick content
   corners, connect, and Start. Verify OBS starts **once**, Recorder shows Recording
   after confirmation, and microphone/desktop audio meters behave as expected.
3. Keep window geometry and OBS transform fixed. Click **three known safe locations**
   inside MapGen once each; note their physical/content-local positions using
   `events.jsonl` after the session. Choose distinct visible landmarks that will not
   navigate or change the reference layout. Do not use browser controls.
4. Switch to Notepad, place it over part of Chrome, and click several times in its
   covered area. Also click outside Chrome. Return to MapGen and click **one more
   known content location**. Avoid extra page clicks; use Alt+Tab to switch apps.
5. Stop, then Generate Heatmaps. In `analysis.json`, `click_presses.included` must be
   **4** for this controlled trial. Notepad/outside clicks are excluded; unsupported
   or ambiguous observations are uncertain and must not enter the MapGen heatmap.
   If included is not 4, inspect reasons and raw observations; do not accept the trial
   or remove inconvenient raw events. Keep recorder controls off the MapGen viewport
   to avoid confusing extra covered-area clicks with the four intended page clicks.
6. Verify `events.jsonl` contains all four page clicks AND other-app clicks (and
   their releases), all movement/scroll callbacks and original monotonic timestamps.
   Every mouse event has `target` and `target_observation`; identity, content-local
   coordinates and classification should match the trial. Query errors should produce
   uncertain records, not disappear from raw data.
7. Export an OBS frame from the matching layout, perform **Align Frame** as described
   above, and verify exactly four rings land on the known interface landmarks.
   Compare ring centers with measured landmarks in image pixels; write measured
   residual X/Y error into a local note under the session folder. Repeat with a
   known OBS crop, scale and letterbox; never accept a visually displaced overlay.
8. In separate trials test moving the window, ordinary resizing, maximizing before
   calibration, and minimizing/restoring. Move across monitors left/above primary
   and across 100%/125%/150% DPI settings. Verify physical pixels/local origin and
   per-size/DPI heatmaps. Switching normal/maximized mid-session should be uncertain;
   stop, recalibrate in the new state and repeat. Check toolbar/content boundaries
   within a pixel, especially after DPI changes; stop/recalibrate if Chrome's UI
   no longer follows the calibrated insets.
9. Cover the exact click point with another window while Chrome remains visible;
   confirm those events are excluded. Try hovering over an uncovered MapGen area
   while another app is foreground: it can still be inside. Test drag capture,
   changed tabs, closed/reopened Chrome, minimized windows, Chrome menus and overlays.
   Unavailable identity/hit tests, changed titles and ambiguous overlays must be
   uncertain. OS-only classification cannot identify same-title tab changes; do
   not use those trials to claim application-content attribution.
10. Repeat start/stop at least five times, including a cold/heavier OBS scene. No
    false failure should occur for an activation that settles within the deadline;
    there must be one OBS recording per session. Inspect startup observations in
    `sync.json`. On a genuine timeout, verify counts keep increasing, Start does
    not issue another request, Check OBS can confirm a settled recording, and Stop
    saves the video. Do not intentionally interrupt a real participant recording.
11. Run the synchronization marker procedure above and audio playback checks at
    both ends. Document measured timing error; frame accuracy is not guaranteed.
12. Repeat the four-click and scroll/movement trials through Zoom remote control,
    leaving the local mouse untouched. Document Windows/Zoom/OBS versions, DPI,
    capture settings and observed counts. If events are absent or uncertain, report
    that configuration unsupported rather than claiming Zoom compatibility.

## Tests and limitations

`python -m unittest discover -s tests -v` runs portable tests for startup-delay
math, correction sign, negative monitor origins, half-open coordinate bounds,
heatmap bin orientation, valid PNG output, session event persistence, simulated
OBS stop/copy, failure recovery, delayed/inconsistent activation, duplicate-start
protection, mocked Windows window enumeration, target identity/occlusion,
movement/resize/DPI transforms, four-click raw-log preservation and frame overlay.
Reference images used by tests are synthetic. They do not validate real OBS, Tk rendering,
Windows input hooks, microphone/desktop audio or Zoom. Run the checklist above
on Windows. No MapGen-specific events, custom media encoder, or automatic OBS
scene/audio configuration are included.

Recordings, JSONL, common media files, local credentials and `.env` are ignored.
Keep sessions under `sessions/` or an external private folder; arbitrary personal
files elsewhere are not automatically protected. Review `git status` before commits.
