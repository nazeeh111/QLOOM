# Supported semantics and export contract

Version 0.1 accepts a Qiskit `QuantumCircuit` or OpenQASM **2.0** with 2–8 qubits, at most 400 input operations and at most 16 classical bits. A device must have exactly the same number of qubits. Spare physical qubits and ancillas are excluded.

Supported gates: `id, h, x, y, z, s, sdg, t, tdg, rx, ry, rz, p, u, u1, u2, u3, cx, cz, swap`, plus barriers and terminal measurements. Parameters must be finite and bound. Standard instruction identities are checked, so a custom gate named `h` cannot masquerade as a Hadamard. Custom declarations, opaque operations, reset, delay, classical conditions, control flow, repeated qubit measurement, classical overwrite and any unitary after measurement are rejected. Only `qelib1.inc` may be included; arbitrary file includes are forbidden. Register size is checked before parsing to prevent oversized allocation.

The native target is a connected, **bidirectional U/CX** graph. Every two-qubit operation must use a graph edge. This release does not claim hardware pulse compilation or arbitrary native gate-set retargeting. U is an arbitrary single-qubit unitary with three parameters. Synthetic error and duration parameters can be set in the Python `Device` interface; no real calibration is included.

## Input and output placement

All arrays use `mapping[logical_qubit] = physical_qubit`. If a logical basis input has bit `q`, its physical location before execution is `initial_mapping[q]`. Decode final quantum outputs with `final_mapping[q]`. Little-endian indexing is used: bit 0 is qubit 0.

The independent checker constructs the complete logical operator from the physical circuit using both permutations. It compares complex amplitudes against the input's operator, **including global phase**, with maximum absolute tolerance `1e-8` for native/Qiskit/QMAP and `1e-7` for BQSKit numerical synthesis. Eight random normalized complex input vectors are also checked. The NumPy interpreter contains explicit gate definitions and never uses Qiskit's Operator or the compiler's rewrite implementation. Tests independently cross-check against Qiskit's operator definitions and deliberate phase/mapping/gate corruptions.

Global phase is a scalar multiplying the entire state; although unobservable in an isolated circuit, preserving it matters when embedding that operator in a controlled computation. QMAP/BQSKit conversions can drop it. The adapter exposes its raw result; the report orchestrator recovers only a single phase scalar from operator overlap, records `global_phase_correction`, restores it, and then applies the full strict check. A scalar correction cannot hide a non-global error. Invalid results remain failed rows.

Full matrices establish the supported unitary prefix. Terminal measurements are preserved by exporting `measure final_mapping[logical] -> original_classical_bit`. Marginal output distributions aggregate to original classical bit destinations, including sparse and reversed assignments. This preserves the measurement instrument on the supported program; general measured/control-flow circuits are outside the contract. A zero-input noisy distribution is never used as logical proof.

## OpenQASM2 is not the full artifact

OpenQASM2 does not encode global phase or logical placement metadata. Use all three files in the CLI bundle:

- `optimized.qasm`: physical circuit, with original classical destinations already restored.
- `metadata.json`: initial/final placement, global phase in radians, measurement destinations and verification.
- `report.json`: all candidates, settings, trained-model digest, baselines, noise assumptions and timing.

To reload a unitary for exact comparison, parse QASM, strip terminal measurements, set its global phase from the sidecar, and pass **both mappings** to `qloom.verify.verify`. Treat QASM alone as a physical program; it is insufficient to reconstruct the logical operator. Studio embeds a reminder and mapping/phase comments in its QASM download, and separately exports the full JSON.

## Local cache contract

`compile_circuit(..., cache_dir=...)` and `qloom compile --cache ...` use a
versioned local report envelope. Its key includes ordered standard operations,
parameters, qubit/classical widths, terminal measurement destinations, global
phase, device data, seed, budget, strategy, model digest and requested options.
Display names, register spelling and ignored barriers do not affect identity.
Different but mathematically equivalent gate sequences may still use separate
entries. There is no floating-point rounding or global-phase normalization in
the identity.

Package source hashes, Python/platform identity, installed numerical/optional
compiler versions and the external-baseline timeout also bind the key. Old-format
entries are not migrated or trusted. Existing files are not deleted automatically.

Before returning a hit, QLOOM checks the envelope checksum and request, reparses
each successful candidate's QASM with restricted includes, checks its operation
list and original classical destinations, restores JSON global phase and both
mappings, and reruns the same full-unitary, measurement and device constraints
as cold compilation. Candidate costs, best selection and Pareto membership are
checked again. Successful cached baselines receive their original fixed
verification tolerance, never a tolerance supplied by the cache.

`cache_hit` is true only after acceptance. `cache.status` is `disabled`, `miss`,
`rejected` (with a reason), or `verified-hit`. A rejected entry triggers fresh
compilation; cache write failures remain diagnostic fields on the valid result.
Unique same-directory temporary files and atomic replacement prevent overlapping
writers from publishing partial JSON.

On a hit, report generation/search timings remain the original observations;
`cache.lookup_verification_s` measures the current lookup and verification.
Model metadata and export guidance are checked against the current request and code.
Simulated noise distributions are checked for valid probabilities, the ideal
distribution and fidelity arithmetic; they remain historical observations, not
newly rerun simulations. Unavailable baseline outcomes, model predictions and
routing history also remain stored observations.
Checksums are accidental-corruption checks, not signatures or authentication.
The cache makes no performance or quantum-advantage claim.

## Limits of evidence

The check is numerical, within an explicit tolerance, and bounded to eight qubits. Random input checks supplement the full operator comparison rather than proving large-system equivalence. No formal proof engine or large-circuit verification is claimed. Synthetic gate-error products are heuristic estimates. Density-matrix results are simulated output-distribution fidelities on the zero logical input, not full state/process fidelities or QPU measurements.
