#!/usr/bin/env python3
"""Recompute saved learned-search outcomes and refit the shipped forest.

Deterministic metrics and tree parameters must agree. Measured times and source
provenance metadata are expected to differ and are excluded from equality.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from qiskit import qasm2

from qloom.compiler import compile_circuit
from qloom.devices import Device
from qloom.surrogate import DEFAULT_MODEL
from qloom.training import source_fingerprint, train


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    work = args.work_dir or root / "work" / "native-reproduction"
    work.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    manifest = json.loads((root / "benchmarks" / "manifest.json").read_text())
    rows = [json.loads(line) for line in (root / "benchmarks" / "results.jsonl").read_text().splitlines()]
    saved = {
        (row["circuit_id"], row["seed"]): row
        for row in rows
        if row["method"] == "learned" and row["status"] == "ok"
    }
    checks = []
    for entry in manifest["circuits"]:
        circuit = qasm2.loads(entry["qasm"], custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
        circuit.global_phase = entry["global_phase"]
        device_data = entry["device"].copy()
        device_data["edges"] = tuple(tuple(e) for e in device_data["edges"])
        device_data["basis_gates"] = tuple(device_data["basis_gates"])
        device = Device(**device_data)
        for seed in manifest["seeds"]:
            report = compile_circuit(
                circuit,
                device,
                budget=manifest["budget"],
                seed=seed,
                strategy="learned",
                baselines=False,
                noisy=False,
            )
            best = next(c for c in report["candidates"] if c["id"] == report["best_id"])
            old = saved[(entry["id"], seed)]
            metrics = ("objective", "two_qubit_gates", "depth", "duration_ns", "estimated_success")
            equal = all(best["metrics"][name] == old["metrics"][name] for name in metrics)
            selections = [int(c["id"].rsplit("-", 1)[1]) for c in report["candidates"]]
            equal = equal and selections == old["evaluated_config_ids"]
            if not equal:
                raise RuntimeError(f"Learned result changed for {entry['id']}, seed {seed}.")
            checks.append(
                {
                    "circuit_id": entry["id"],
                    "seed": seed,
                    "metrics_exact": True,
                    "selection_exact": True,
                    "verified_candidates": len(report["candidates"]),
                    "max_equivalence_error": max(
                        c["verification"]["max_error"] for c in report["candidates"]
                    ),
                }
            )
    original = json.loads(DEFAULT_MODEL.read_text())
    original_hash = sha256(DEFAULT_MODEL.read_bytes()).hexdigest()
    fresh_path = work / "surrogate.json"
    fitted = train(work / "training", count=120, seed=20261025, model_path=fresh_path)
    fresh = json.loads(fresh_path.read_text())
    trees_equal = fresh["trees"] == original["trees"]
    if not trees_equal:
        raise RuntimeError("Fresh forest tree parameters differ from the shipped model.")
    result = {
        "schema_version": "1.0",
        "passed": True,
        "learned_search_runs_reproduced": len(checks),
        "heldout_circuit_device_instances": len(manifest["circuits"]),
        "fresh_verified_search_candidates": sum(row["verified_candidates"] for row in checks),
        "retrained_unique_circuits": fitted["training_circuits"],
        "retrained_verified_candidates": fitted["training_rows"],
        "forest_parameters_exact": trees_equal,
        "feature_schema_exact": fresh["feature_names"] == original["feature_names"],
        "original_model_sha256": original_hash,
        "reproduced_model_sha256": sha256(fresh_path.read_bytes()).hexdigest(),
        "original_training_source_sha256": original["training"]["source_sha256"],
        "reproduction_source_sha256": source_fingerprint(),
        "model_hash_note": "Metadata hashes and timing-bearing label hashes differ; all 48 exported tree parameter arrays match exactly.",
        "timing_note": "Wall time is measured evidence and intentionally excluded from deterministic equality.",
        "external_note": "External compiler baseline rows were measured in the full experiment; this reproduction reruns native search and training only.",
        "elapsed_s": perf_counter() - started,
        "checks": checks,
    }
    target = root / "benchmarks" / "reproduction.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}, indent=2))


if __name__ == "__main__":
    main()
