# Synthetic evidence only

`python -m examples.synthetic_demo` generates a small mock Home/Editor MKV, raw
mouse events, two annotated stable segments, three visual AOIs and real saved-frame analysis under
ignored `sessions/synthetic-demo/`. It does not access MapGen or capture anyone's
screen. FFmpeg/ffprobe must be on PATH.

The committed PNGs below were generated from that synthetic video, not participant
recordings. They demonstrate state-specific backgrounds and counted clicks, not
Windows, UIA, OBS, synchronization or Zoom accuracy.

| Synthetic Home | Synthetic Editor |
|---|---|
| ![Home density](synthetic-home-density.png) | ![Editor density](synthetic-editor-density.png) |
| ![Home numbered clicks](synthetic-home-clicks.png) | ![Editor numbered clicks](synthetic-editor-clicks.png) |
| ![Home visual regions](synthetic-home-regions.png) | ![Editor visual regions](synthetic-editor-regions.png) |

The full example also produces movement density, optional smoothed versions, raw
count grids, per-click actual-frame context and CSV/JSON provenance/QA. Timing
remains unverified because no independent real-world onset measurements exist.

The Navigation, Gallery and Editor AOIs receive 1, 1 and 2 synthetic presses
respectively. Their bounded observed cursor times are 0.08, 0.08 and 0.16 seconds;
long stationary gaps are intentionally not counted as full hover time. Exports
include clean screenshots, transparent density layers and region assignment CSV/JSON.
