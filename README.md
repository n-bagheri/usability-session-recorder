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
- Enter capture rectangle `left,top,width,height` in **physical desktop pixels**.
  Default is the entire virtual desktop; monitors left/above primary have negative
  coordinates. For a window crop, enter its desktop rectangle yourself and match
  the OBS source. The app does not infer an OBS transform or crop.
- Keep the captured window, monitor arrangement, DPI, and OBS transform fixed
  during a session. Events retain foreground-window rectangle and desktop bounds
  for later analysis, but foreground window is not necessarily the captured window.
- Start Session. The input hook begins before requesting OBS StartRecord, so
  events during startup can have negative estimated video times. Status confirms
  OBS active/unpaused and logs its current duration. Do a short input/audio check.
- Use Sync Marker near the beginning and end. See synchronization below.
- Stop Session. Wait for OBS acknowledgement and video copying. The OBS original
  is retained. Generate Heatmaps and select the completed session folder.
- On errors, read the dialog. If start or stop timed out, inspect OBS and retry Stop
  before closing. Recording may still be active. Metadata and raw events are
  flushed during capture; interrupted sessions may need manual video recovery
  from OBS's recording folder. If copying fails, retry Stop with sufficient disk
  space; the saved original output path is retained. Never start another recording
  while recovering an uncertain session.

## Files and synchronization

Each unique session folder contains:

- `video.mkv` (or OBS's selected extension): copied after recording stops.
- `events.jsonl`: monotonic nanoseconds, mouse type, physical X/Y, button/press,
  scroll deltas, desktop and foreground-window geometry. Moves are capped at
  approximately 60 Hz, clicks/releases and scrolls are not throttled.
- `metadata.json`: UTC creation time, mode, capture rectangle, OBS request/response
  timestamps, output path, state, counts and any observed input errors.
- `sync.json`: OBS duration samples, origin estimate, half request round-trip
  times, marker times, and a manually measured correction.
- `move_heatmap.png` and `click_heatmap.png`: 128×128 event-count bins, top-left
  origin, axes in physical desktop pixels. Clicks count presses only. Out-of-crop
  events are retained in raw data but excluded from heatmaps. Movement heatmaps
  represent sampled movement density, **not dwell time**. No video overlay is
  inferred. Geometry changes require separate analysis rather than blindly
  combining windows or screens.

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

## Tests and limitations

`python -m unittest discover -s tests -v` runs portable tests for startup-delay
math, correction sign, negative monitor origins, half-open coordinate bounds,
heatmap bin orientation, valid PNG output, session event persistence, simulated
OBS stop/copy, and failure recovery. They do not validate real OBS, Tk rendering,
Windows input hooks, microphone/desktop audio or Zoom. Run the checklist above
on Windows. No MapGen-specific events, custom media encoder, or automatic OBS
scene/audio configuration are included.

Recordings, JSONL, common media files, local credentials and `.env` are ignored.
Keep sessions under `sessions/` or an external private folder; arbitrary personal
files elsewhere are not automatically protected. Review `git status` before commits.
