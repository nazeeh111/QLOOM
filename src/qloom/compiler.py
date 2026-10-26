"""Verified budgeted configuration search and reproducible report assembly."""

import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import numpy as np
from qiskit import QuantumCircuit

from .circuits import export_qasm, load_qasm, operations, serialize_input, split_circuit
from .cost import metrics, pareto
from .devices import Device, make_device
from .features import features
from .interfaces import CompilationReport
from .routing import CONFIGS, native_compile
from .surrogate import Surrogate
from .verify import verify


def candidate_record(
    reference,
    physical,
    initial,
    final,
    device,
    measurements,
    n_clbits,
    identifier,
    config,
    elapsed,
    history=None,
    seed=0,
    tolerance=1e-8,
):
    verification = verify(reference, physical, initial, final, seed, tolerance)
    if not verification["passed"]:
        raise ValueError(
            f"Candidate {identifier} failed independent equivalence: {verification['max_error']:.3g}"
        )
    qasm = export_qasm(physical, measurements, final, n_clbits)
    if measurements:
        from qiskit import qasm2

        from .circuits import validate
        from .verify import verify_measurement_export

        exported = qasm2.loads(qasm, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
        validate(exported, max_operations=None)
        actual = [
            [exported.find_bit(i.qubits[0]).index, exported.find_bit(i.clbits[0]).index]
            for i in exported.data
            if i.operation.name == "measure"
        ]
        if actual != [[final[q], c] for q, c in measurements]:
            raise ValueError("Export changed classical measurement destinations.")
        measurement_check = verify_measurement_export(reference, exported, initial, measurements, seed)
        if not measurement_check["measurement_passed"]:
            raise ValueError("Export failed independent measured-output simulation.")
        verification.update(measurement_check)
    m = metrics(physical, device, elapsed)
    return {
        "id": identifier,
        "config": config,
        "metrics": m,
        "verification": verification,
        "initial_mapping": list(initial),
        "final_mapping": list(final),
        "operations": operations(physical),
        "history": history or [],
        "qasm": qasm,
        "global_phase": float(physical.global_phase),
        "model_prediction": None,
        "elapsed_s": elapsed,
    }


def compile_circuit(
    circuit: QuantumCircuit | str,
    device: Device | None = None,
    budget: int = 4,
    seed: int = 0,
    strategy: str = "learned",
    model_path=None,
    baselines: bool = True,
    noisy: bool = True,
    cache_dir: str | Path | None = None,
    graph_aware: bool = True,
) -> CompilationReport:
    """Compile in exactly `budget` native evaluations; independently verify each.

    Training is offline. Feature extraction/model inference do not count as native
    evaluations, and their wall time remains in elapsed_s. Baseline wall time is
    reported separately. v0.1 excludes spare physical qubits and dynamic circuits.
    """
    start = perf_counter()
    qc = load_qasm(circuit) if isinstance(circuit, str) else circuit.copy()
    reference, measurements = split_circuit(qc)
    device = device or make_device("line", qc.num_qubits)
    if device.n_qubits != qc.num_qubits:
        raise ValueError("Circuit and device must have equal width (no ancillas in v0.1).")
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= len(CONFIGS):
        raise ValueError(f"budget must be an integer in 1..{len(CONFIGS)}")
    if strategy not in {"learned", "random", "heuristic"}:
        raise ValueError("strategy must be learned, random or heuristic")
    if not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer in 0..2^32-1")
    model = Surrogate(model_path) if strategy == "learned" else None
    cache_key = sha256(
        json.dumps(
            {
                "input": serialize_input(qc),
                "device": device.to_dict(),
                "budget": budget,
                "seed": seed,
                "strategy": strategy,
                "model": model.sha256 if model else None,
                "baselines": baselines,
                "noisy": noisy,
                "graph_aware": graph_aware,
                "version": "0.1.0",
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cache_path = Path(cache_dir) / f"{cache_key}.json" if cache_dir else None
    if cache_path and cache_path.exists():
        report = json.loads(cache_path.read_text())
        report["cache_hit"] = True
        return report
    scores = [None] * len(CONFIGS)
    if strategy == "learned":
        order, scores = model.rank(reference, device, graph_aware)
    elif strategy == "random":
        order = np.random.default_rng(seed).permutation(len(CONFIGS)).tolist()
    else:
        # No-evaluation heuristic: placement distance and potential rewrites.
        vals = [features(reference, device, c) for c in CONFIGS]
        order = sorted(
            range(len(CONFIGS)),
            key=lambda i: (
                vals[i][13] * vals[i][2] - (vals[i][17] * 2 if CONFIGS[i].rewrite else 0),
                not CONFIGS[i].rewrite,
                CONFIGS[i].routing != "lookahead",
                i,
            ),
        )
    candidates = []
    physical_by_id = {}
    search_start = perf_counter()
    for i in order[:budget]:
        t = perf_counter()
        physical, initial, final, history = native_compile(reference, device, CONFIGS[i])
        elapsed = perf_counter() - t
        identifier = f"qloom-{i:02d}"
        c = candidate_record(
            reference,
            physical,
            initial,
            final,
            device,
            measurements,
            qc.num_clbits,
            identifier,
            CONFIGS[i].to_dict(),
            elapsed,
            history,
            seed,
        )
        c["model_prediction"] = scores[i]
        c["elapsed_s"] = perf_counter() - search_start
        candidates.append(c)
        physical_by_id[identifier] = (physical, final)
    search_s = perf_counter() - search_start
    best = min(candidates, key=lambda c: (c["metrics"]["objective"], c["id"]))
    optimizer_time_s = perf_counter() - start
    baseline_records = []
    baseline_physical = None
    if baselines or noisy:
        from .baselines import compile_baseline

        names = (
            ["qiskit-0", "qiskit-1", "qiskit-2", "qiskit-3", "qmap", "bqskit"] if baselines else ["qiskit-0"]
        )
        for name in names:
            try:
                physical, initial, final, meta = compile_baseline(reference, device, name, seed)
                phase_correction = 0.0
                if name in {"qmap", "bqskit"}:
                    # External conversion/synthesis may drop global phase. Recover
                    # and record the missing scalar, then verify strict equality.
                    from .verify import logical_matrix

                    u = logical_matrix(reference, list(range(qc.num_qubits)), list(range(qc.num_qubits)))
                    v = logical_matrix(physical, initial, final)
                    phase_correction = -float(np.angle(np.vdot(u, v)))
                    physical.global_phase += phase_correction
                c = candidate_record(
                    reference,
                    physical,
                    initial,
                    final,
                    device,
                    measurements,
                    qc.num_clbits,
                    name,
                    {"compiler": name},
                    meta["elapsed_s"],
                    seed=seed,
                    tolerance=1e-7 if name == "bqskit" else 1e-8,
                )
                c.update(
                    {
                        "name": name,
                        "status": "ok",
                        "metadata": meta,
                        "global_phase_correction": phase_correction,
                    }
                )
                baseline_records.append(c)
                if name == "qiskit-0":
                    baseline_physical = (physical, final)
            except Exception as exc:
                baseline_records.append(
                    {
                        "id": name,
                        "name": name,
                        "status": "unavailable-or-failed",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )
    noise = {"method": "not-run", "assumptions": "Enable noisy=True and install the research extras."}
    if noisy and baseline_physical:
        try:
            from .noise import compare_noise

            noise = compare_noise(
                reference,
                physical_by_id[best["id"]],
                baseline_physical,
                device,
                measurements,
                qc.num_clbits,
                seed,
            )
        except ImportError as exc:
            noise = {"method": "unavailable", "assumptions": str(exc)}
    report = {
        "schema_version": "1.0",
        "seed": seed,
        "strategy": strategy,
        "budget": budget,
        "device": device.to_dict(),
        "input": serialize_input(qc),
        "candidates": candidates,
        "best_id": best["id"],
        "pareto_ids": pareto(candidates),
        "baselines": baseline_records,
        "noise": noise,
        "model": model.metadata() if model else {"name": strategy},
        "search_time_s": search_s,
        "optimizer_time_s": optimizer_time_s,
        "elapsed_s": perf_counter() - start,
        "cache_hit": False,
        "export_note": "QASM2 omits global phase and layout semantics. Export JSON alongside QASM. Initialize inputs using initial_mapping; interpret unitary outputs using final_mapping. Exported measurement statements already map logical results to original classical bit indices. All model noise is simulated; no real QPU execution.",
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp = cache_path.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2))
        temp.replace(cache_path)
    return report
