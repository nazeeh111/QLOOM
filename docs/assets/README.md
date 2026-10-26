# Editable brand and architecture assets

`architecture.svg`, `social-preview.svg` and `logo.svg` are original editable vector masters. `build_diagrams.py` reconstructs them. PNGs were rendered from the current masters with Flowcraft's local SVG renderer and visually inspected.

Architecture source-to-element map:
- `training-evaluations`, `model-fit`, `json-model`: `src/qloom/training.py` and `surrogate.py`; real native evaluations, normalized objective regression, ExtraTrees exported as non-executable JSON.
- `graph-features`: `src/qloom/features.py`; graph summaries and candidate configuration features, not a graph neural network.
- `input-validation`: `circuits.py`, `devices.py`; bounded gates, equal logical/physical widths, synthetic bidirectional U/CX devices.
- `budgeted-ranking`, `native-compiler`: `compiler.py`, `routing.py`; rank 24 candidates, evaluate the requested hard budget, native rewrites and mapping-aware SWAP routing.
- `semantics-gate`: `verify.py`; independent NumPy full matrix, strict global phase, logical input/output mappings and randomized input checks.
- `hardware-evaluation`: `cost.py`, `noise.py`; physical constraints, timing/cost proxies and optional density-matrix output simulation. Noise is not a proof of circuit equivalence.
- `baselines`: `baselines.py` and `compiler.py`; explicit separately measured baseline effort and independent semantics checks.
- `studio-export`: report schema in `compiler.py`, CLI/server and `src/qloom/web`.

The social-preview circuit is explicitly illustrative brand line art, not a benchmark circuit or result. The launch video uses a real report-derived circuit excerpt and current Studio screenshot. All original QLOOM visual sources follow the repository license. See the launch asset attribution for its third-party animation runtime.
