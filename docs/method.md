# How QLOOM works

QLOOM searches 24 deterministic compiler configurations: four placements (`identity`, centrality-ranked, interaction-refined, reverse-interaction-refined), three routing policies (move control, move target, lookahead), and two rewrite states. The configuration's lookahead window is six upcoming CX interactions. The selected strategy changes which configurations are actually compiled. A budget of four means exactly four native compiler evaluations, not all 24 followed by a favorable selection.

## Native transformations

Before standard gate lowering, a traversal cancels inverse operations across gates proved to commute. It folds matching rotation axes and never reduces angles modulo 2π, which would risk discarding global phase. The commutation rules cover disjoint supports, compatible CX pairs, Z-like operations on CX controls and X-like operations on CX targets. An optional second sweep removes routing-induced CX cancellations.

Qiskit's `BasisTranslator` supplies standard gate identities to U/CX. It receives no device, layout or routing request. The QLOOM path does not call `qiskit.transpile`; separate baseline adapters do. Placement uses weighted interaction graphs and deterministic pair-swap refinement. Routing inserts three-CX SWAPs on hardware edges and updates token locations. Each chosen SWAP strictly reduces the current interaction's shortest-path distance, guaranteeing progress on connected devices. Lookahead scores distances for upcoming interactions to select among those swaps. Initial/final maps and actual transformation events are retained.

This is an original inspectable compiler implementation over established techniques, not a new mathematical routing theorem or a claim that learned quantum compilation is novel. The search varies pass activation/order (rewrite before/after lowering/routing), layout and routing. It does not learn arbitrary gate decompositions or synthesize a new pass library; alternate native decomposition families are future work.

## Learned budget allocation

Offline labels are measured outputs of the native compiler, not Qiskit transpile labels. A compact 48-tree ExtraTrees ensemble predicts the cost of a configuration relative to input two-qubit count. Twenty-eight features describe the circuit interaction graph, processor graph, placement distances, rewrite opportunities, synthetic noise, and configuration. The features include graph density, degree dispersion, diameter and a Laplacian gap. This is graph-aware feature engineering, **not a graph neural network** and not reinforcement learning.

At runtime the JSON-only tree interpreter ranks configurations without importing scikit-learn. The first `budget` ranked configurations are compiled and independently verified. No invalid candidate can win. The final choice minimizes:

`CX count + 0.04 × depth + 8 × (-log(estimated_success))`

`estimated_success = (1 − two_qubit_error)^CX × (1 − single_qubit_error)^single`

This fixed, transparent scalar objective guides selection. The report also identifies nondominated candidates across CX count, duration and estimated failure probability. Duration is a dependency-aware earliest-start schedule under synthetic fixed gate durations; it excludes pulse scheduling, idle decoherence and readout duration. All graph edges currently share the same error/duration parameters. Topology-aware behavior should not be mistaken for per-edge calibration-aware routing.

## Fair comparisons

Learned, random and heuristic search receive the same native evaluation budget and candidate set. Exhaustive search is a 24-evaluation oracle. Offline training and verification costs are reported separately. External compilers use identical physical widths, bidirectional graphs and U/CX basis, but their internal search budgets differ. Report their measured invocation time and configuration; a single call is not automatically equal to a QLOOM evaluation. QMAP/BQSKit run in bounded subprocesses, including cold worker startup in measured wall time.

See [experiment protocol and actual results](experiments.md), [research foundations](research-foundations.md), and [semantics](semantics.md). The evidence is a small synthetic CPU study, with results and failures published. It cannot establish general compiler superiority or performance on real processors.
