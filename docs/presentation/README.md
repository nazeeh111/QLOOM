# Circuit figure provenance

`circuit-handoff.png` and the editable SVG render `../../examples/live-studio/report.json` at source commit `ddcce9317bdc59e053f6b6fec3cedf43b9203111`.

This is a presentation of a retained example, not a new compiler or benchmark run. The input gates are H(q0), CX(q0,q2), Ry(0.31)(q1). The selected `best_id` is `qloom-07`; its physical operations are U(p1), U(p2), CX(p1,p0). Exact U angles remain in the JSON. Initial and final logical-to-physical mappings are `[1, 2, 0]`. Original terminal measurements q0→c2, q1→c1, q2→c0 are omitted from the compact drawing, but remain in QASM and the source record.

The saved numerical check reports `passed: true`, maximum operator error `1.401642967028923e-16` against tolerance `1e-8`, with global phase and eight randomized inputs included. This is finite numerical evidence, not a formal proof or hardware result. The synthetic line-3 device and two-candidate budget belong to this example; they are different from the five-qubit/eight-candidate Studio capture and the historical four-budget study.

Gate order, positions, mappings and the check flag were read directly from the source. There is no metric rescaling or inferred routing event. No SWAP appears in this selected physical circuit. Both the text above and the original JSON are accessible alternatives to the image.

## Regenerate the presentation

With existing NumPy and Matplotlib, run `python docs/presentation/render.py` (desktop) and `python docs/presentation/render.py --mobile` (stacked/narrow) from the repository root. It reads the stored source JSON above and writes the PNG, editable SVG and `manifest.json` beside this note. It performs no new solve, fit or experiment. Matplotlib 3.11.2 and NumPy 2.5.4 were used for these outputs. The manifest records exact inputs, transformations and output hashes.
