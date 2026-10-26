# QLOOM launch film

`brag.mp4` is the final 20-second, 1920×1080, 30fps film. `brag.jpg` is its selected settled Studio poster, also baked into frame zero. `share-copy.txt` is a ready-to-use caption. The script uses a genuine retained demo and a current Studio screenshot; it makes no claim of universal superiority over existing compilers.

Editable source is `composition/index.html`, with local assets and the original audio generator in `build_assets.py`. `brag-plan.md`, `composition-brief.md`, and `composition/DESIGN.md` retain the creative direction. `composition/assets/demo-evidence.json` records the source report hash.

To regenerate data-derived assets and audio, run `python launch/build_assets.py` from the repository with NumPy installed. If the recorded experiment or screenshot changes, inspect the resulting source and re-render before distributing. Copy the current `docs/assets/studio.png` to `composition/assets/studio.png`.

The composition follows the HyperFrames HTML/GSAP contract. It was rendered locally with pinned HyperFrames 0.8.33, installed Chrome, FFmpeg and one worker. A compatible HyperFrames CLI can lint, inspect, and render `composition/`; retain the specified 20 seconds and 1920×1080 canvas. No paid API, GPU dependency or narration is needed. Runtime differences can change font rasterization; inspect fresh renders. See `ATTRIBUTION.md` for GSAP’s separate copyright and license notice.

After a successful render, extract a settled Studio frame around 7 seconds as `brag.jpg`, then replace only frame zero with that poster while copying the audio stream. This is a thumbnail treatment; the presentation begins immediately afterward. Final decode and frame-count checks are recorded in `VERIFICATION.md`.
