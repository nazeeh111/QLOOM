"""Held-out, budget-matched experiments with honest external-baseline scope.

Circuit inputs shared across topologies form one uncertainty cluster. Seeds are
repeated measurements, not extra independent circuits. CIs bootstrap input clusters.
"""

from __future__ import annotations

import json
import platform
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from qiskit import qasm2

from .baselines import BASELINE_NAMES, compile_baseline
from .compiler import compile_circuit
from .cost import metrics
from .devices import make_device
from .examples import generate
from .features import features
from .routing import CONFIGS, native_compile
from .surrogate import DEFAULT_MODEL, Surrogate
from .training import circuit_fingerprint, source_fingerprint
from .verify import logical_matrix, verify

TEST_FAMILIES = ("random", "ghz", "mirror", "qaoa", "qft", "starphase")
TEST_TOPOLOGIES = ("line", "ring", "grid", "star")


def test_specs(quick: bool = False):
    families = ("random", "qft") if quick else TEST_FAMILIES
    for fi, family in enumerate(families):
        for ti, topology in enumerate(TEST_TOPOLOGIES):
            n = 4 + ((fi + ti) % 2)
            seed = 10001 + 100 * fi + ti
            qc = generate(family, n, seed, layers=2 + (fi % 2))
            qc.global_phase = 0.173 * (fi + 1)
            yield (
                {
                    "id": f"test-{family}-{topology}-{n}",
                    "family": family,
                    "topology": topology,
                    "n_qubits": n,
                    "seed": seed,
                    "heldout_topology": topology == "star",
                    "heldout_family": family in {"ghz", "qft", "starphase"},
                },
                qc,
            )


def _native_row(qc, device, indices, name, seed):
    started = perf_counter()
    values = []
    compile_times = []
    for index in indices:
        t = perf_counter()
        physical, initial, final, _ = native_compile(qc, device, CONFIGS[index])
        compile_times.append(perf_counter() - t)
        checked = verify(qc, physical, initial, final, seed)
        if not checked["passed"]:
            raise RuntimeError(f"{name} candidate {index} failed verification: {checked}")
        value = metrics(physical, device, compile_times[-1])
        values.append((value, index, checked))
    best = min(values, key=lambda value: (value[0]["objective"], value[1]))
    return {
        "method": name,
        "seed": seed,
        "status": "ok",
        "budget": len(indices),
        "evaluated_config_ids": indices,
        "best_config_id": best[1],
        "metrics": best[0],
        "verification": best[2],
        "wall_time_s": perf_counter() - started,
        "native_compile_time_s": sum(compile_times),
    }


def _external_row(qc, device, name, seed):
    started = perf_counter()
    try:
        physical, initial, final, metadata = compile_baseline(qc, device, name, seed)
        phase_correction = 0.0
        pre_correction_error = None
        if name in {"qmap", "bqskit"}:
            identity = list(range(qc.num_qubits))
            u = logical_matrix(qc, identity, identity)
            v = logical_matrix(physical, initial, final)
            pre_correction_error = float(np.max(np.abs(u - v)))
            phase_correction = -float(np.angle(np.vdot(u, v)))
            physical.global_phase += phase_correction
        checked = verify(qc, physical, initial, final, seed, tolerance=1e-7 if name == "bqskit" else 1e-8)
        if not checked["passed"]:
            raise ValueError(f"Independent equivalence failed: {checked}")
        result = metrics(physical, device, metadata["elapsed_s"])
        row = {
            "method": name,
            "seed": seed,
            "status": "ok",
            "budget": "one compiler invocation",
            "metrics": result,
            "verification": checked,
            "wall_time_s": perf_counter() - started,
            "metadata": metadata,
            "global_phase_correction": phase_correction,
            "pre_phase_correction_max_error": pre_correction_error,
            "initial_mapping": initial,
            "final_mapping": final,
        }
        return row, (physical, final)
    except Exception as exc:
        return {
            "method": name,
            "seed": seed,
            "status": "failed-or-unavailable",
            "reason": f"{type(exc).__name__}: {exc}",
            "wall_time_s": perf_counter() - started,
        }, None


def _cluster_ci(values: list[float], seed: int = 20261025, weights: list[float] | None = None) -> list[float]:
    if len(values) < 2:
        return [float(values[0]), float(values[0])] if values else [0.0, 0.0]
    rng = np.random.default_rng(seed)
    a = np.asarray(values)
    indices = rng.integers(0, len(a), size=(2000, len(a)))
    w = np.ones(len(a)) if weights is None else np.asarray(weights)
    means = np.sum(a[indices] * w[indices], axis=1) / np.sum(w[indices], axis=1)
    return np.quantile(means, [0.025, 0.975]).tolist()


def summarize(rows: list[dict], manifest: list[dict], budget: int, seeds: tuple[int, ...]) -> dict[str, Any]:
    successful = [r for r in rows if r["status"] == "ok"]
    methods = []
    id_to_cluster = {spec["id"]: spec["sha256"] for spec in manifest}
    for name in sorted({r["method"] for r in rows if r["method"] != "noise-comparison"}):
        group = [r for r in successful if r["method"] == name]
        failed = [r for r in rows if r["method"] == name and r["status"] != "ok"]
        if not group:
            methods.append({"name": name, "instances": 0, "failures": len(failed)})
            continue
        ids = sorted({r["circuit_id"] for r in group})
        clusters = sorted({id_to_cluster[i] for i in ids})
        buckets = [
            [r["regret"] for r in group if id_to_cluster[r["circuit_id"]] == cluster] for cluster in clusters
        ]
        cluster_regret = [float(np.mean(bucket)) for bucket in buckets]
        cluster_weights = [len(bucket) for bucket in buckets]
        method = {
            "name": name,
            "instances": len(group),
            "circuit_device_instances": len(ids),
            "unique_circuit_clusters": len(clusters),
            "failures": len(failed),
            "mean_objective": float(np.mean([r["metrics"]["objective"] for r in group])),
            "mean_wall_time_s": float(np.mean([r["wall_time_s"] for r in group])),
            "mean_regret": float(np.average(cluster_regret, weights=cluster_weights)),
            "regret_ci95": _cluster_ci(cluster_regret, weights=cluster_weights),
            "oracle_hit_rate": float(np.mean([abs(r["regret"]) < 1e-8 for r in group])),
        }
        for metric in ("two_qubit_gates", "depth", "duration_ns", "estimated_success"):
            method[f"mean_{metric}"] = float(np.mean([r["metrics"][metric] for r in group]))
        methods.append(method)
    by_method_id = {(r["method"], r["circuit_id"], r["seed"]): r for r in successful}
    paired = []
    for baseline in ("random", "heuristic", "no-graph", "no-rewrite", "qiskit-3", "qmap", "bqskit"):
        cluster_values = {}
        outcomes = []
        for spec in manifest:
            differences = []
            for seed in seeds:
                a = by_method_id.get(("learned", spec["id"], seed))
                b = by_method_id.get((baseline, spec["id"], seed))
                if a and b:
                    diff = a["metrics"]["objective"] - b["metrics"]["objective"]
                    differences.append(diff)
                    outcomes.append(diff)
            if differences:
                cluster_values.setdefault(spec["sha256"], []).extend(differences)
        if cluster_values:
            clusters = [float(np.mean(values)) for values in cluster_values.values()]
            weights = [len(values) for values in cluster_values.values()]
            paired.append(
                {
                    "baseline": baseline,
                    "unique_circuit_clusters": len(clusters),
                    "mean_objective_difference_learned_minus_baseline": float(
                        np.average(clusters, weights=weights)
                    ),
                    "ci95": _cluster_ci(clusters, weights=weights),
                    "wins": sum(x < -1e-8 for x in outcomes),
                    "ties": sum(abs(x) <= 1e-8 for x in outcomes),
                    "losses": sum(x > 1e-8 for x in outcomes),
                    "denominator_seeded_runs": len(outcomes),
                }
            )
    unsuccessful = []
    for row in successful:
        if row["method"] != "learned":
            continue
        oracle = row["oracle_objective"]
        if row["metrics"]["objective"] > oracle + 1e-8:
            unsuccessful.append(
                {
                    "circuit_id": row["circuit_id"],
                    "seed": row["seed"],
                    "objective": row["metrics"]["objective"],
                    "oracle": oracle,
                    "regret": row["regret"],
                }
            )
    return {
        "schema_version": "1.0",
        "circuits": len(manifest),
        "unique_circuit_inputs": len(set(id_to_cluster.values())),
        "seeds": list(seeds),
        "budget": budget,
        "methods": methods,
        "paired_comparisons": paired,
        "unsuccessful_cases": sorted(unsuccessful, key=lambda row: -row["regret"])[:12],
        "failed_rows": [r for r in rows if r["status"] not in {"ok", "noise-only"}],
        "noise": [r for r in rows if r.get("noise")],
        "notes": [
            "Synthetic bidirectional U/CX processors; equal physical and logical width.",
            f"{len(manifest)} held-out circuit-device instances. Some numerical inputs repeat across topology; unique circuit hashes define uncertainty clusters. Seeds repeat the same instances.",
            "Native search methods get exactly four candidate evaluations, with feature/inference and verification wall time included.",
            "Exhaustive oracle is best of QLOOM's 24 native configurations, not the global optimum.",
            "External compilers get one invocation; their internal search budgets differ. Quality and wall time must be read together.",
            "QMAP has no seed argument and is deterministic; repeated requested seeds do not create stochastic runs.",
            "BQSKit is restricted to four named representative circuit-device instances, three seeds each, with a 45-second invocation timeout.",
            "Graph-free model is refitted on identical labels with all 13 graph features removed. No-rewrite ablation restricts the configuration space.",
            "95% CIs use 2,000 cluster-bootstrap draws over unique circuit input hashes, retaining repeated topology/seed rows within each cluster; never over individual gate labels.",
            "Distribution fidelity is an exact simulated zero-input output metric, not a logical equivalence test or QPU measurement.",
        ],
    }


def run_experiments(
    output: str | Path, quick: bool = False, seeds: tuple[int, ...] = (0, 1, 2)
) -> dict[str, Any]:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    model = Surrogate()
    no_graph_path = DEFAULT_MODEL.with_name("surrogate-no-graph.json")
    if not no_graph_path.exists():
        raise ValueError("Train the retrained graph-free ablation before benchmarking.")
    graph_free = Surrogate(no_graph_path)
    manifest_candidates = [
        output.parent / "models" / "training-manifest.json",
        output.parent.parent / "models" / "training-manifest.json",
        Path.cwd() / "models" / "training-manifest.json",
    ]
    train_manifest_path = next((path for path in manifest_candidates if path.exists()), None)
    if train_manifest_path is None:
        raise ValueError(
            "Training manifest not found. Run from the source checkout with models/training-manifest.json, or place the output beside that models directory."
        )
    training = json.loads(train_manifest_path.read_text())
    train_hashes = {r["sha256"] for r in training["circuits"]}
    rows, manifest, exhaustive_rows, replay_rows = [], [], [], []
    budget = 4
    bq_subset = {"test-random-line-4", "test-mirror-star-5", "test-qft-ring-5", "test-starphase-grid-5"}
    raw = (output / "results.jsonl").open("w")

    def save(row):
        rows.append(row)
        raw.write(json.dumps(row, separators=(",", ":")) + "\n")
        raw.flush()

    try:
        for spec, qc in test_specs(quick):
            fingerprint = circuit_fingerprint(qc)
            if fingerprint in train_hashes:
                raise RuntimeError(f"Train/test exact-input overlap: {spec['id']}")
            device = make_device(spec["topology"], spec["n_qubits"])
            manifest.append(
                {
                    **spec,
                    "sha256": fingerprint,
                    "qasm": qasm2.dumps(qc),
                    "global_phase": float(qc.global_phase),
                    "device": device.to_dict(),
                }
            )
            oracle_started = perf_counter()
            oracle_values = []
            for index, config in enumerate(CONFIGS):
                physical, initial, final, _ = native_compile(qc, device, config)
                checked = verify(qc, physical, initial, final, seeds[0])
                if not checked["passed"]:
                    raise RuntimeError(f"Held-out exhaustive candidate failed: {spec['id']}/{index}")
                result = metrics(physical, device)
                oracle_values.append(result["objective"])
                exhaustive_rows.append(
                    {
                        "circuit_id": spec["id"],
                        "config_id": index,
                        "config": config.to_dict(),
                        "metrics": result,
                        "verification": checked,
                    }
                )
            oracle_objective = min(oracle_values)
            save(
                {
                    "circuit_id": spec["id"],
                    "method": "oracle-24",
                    "seed": seeds[0],
                    "status": "ok",
                    "budget": 24,
                    "wall_time_s": perf_counter() - oracle_started,
                    "metrics": min(
                        [r["metrics"] for r in exhaustive_rows if r["circuit_id"] == spec["id"]],
                        key=lambda r: r["objective"],
                    ),
                    "oracle_objective": oracle_objective,
                    "regret": 0.0,
                }
            )
            native_best_by_seed = {}
            for seed in seeds:
                for name in ("learned", "random", "heuristic", "no-graph"):
                    t = perf_counter()
                    report = compile_circuit(
                        qc,
                        device,
                        budget=budget,
                        seed=seed,
                        strategy="learned" if name == "no-graph" else name,
                        model_path=no_graph_path if name == "no-graph" else None,
                        graph_aware=name != "no-graph",
                        baselines=False,
                        noisy=False,
                    )
                    best = next(c for c in report["candidates"] if c["id"] == report["best_id"])
                    row = {
                        "circuit_id": spec["id"],
                        "method": name,
                        "seed": seed,
                        "status": "ok",
                        "budget": budget,
                        "wall_time_s": perf_counter() - t,
                        "search_time_s": report["search_time_s"],
                        "native_compile_time_s": sum(
                            c["metrics"]["compile_time_s"] for c in report["candidates"]
                        ),
                        "metrics": best["metrics"],
                        "verification": best["verification"],
                        "best_config_id": int(best["id"].rsplit("-", 1)[1]),
                        "evaluated_config_ids": [
                            int(c["id"].rsplit("-", 1)[1]) for c in report["candidates"]
                        ],
                        "model_sha256": report["model"].get("sha256"),
                        "oracle_objective": oracle_objective,
                        "regret": (best["metrics"]["objective"] - oracle_objective)
                        / max(oracle_objective, 1e-12),
                    }
                    save(row)
                    if name == "learned":
                        native_best_by_seed[seed] = best
                t = perf_counter()
                order, _ = model.rank(qc, device)
                restricted = [i for i in order if not CONFIGS[i].rewrite][:budget]
                row = _native_row(qc, device, restricted, "no-rewrite", seed)
                row["wall_time_s"] = perf_counter() - t
                row.update(
                    circuit_id=spec["id"],
                    oracle_objective=oracle_objective,
                    regret=(row["metrics"]["objective"] - oracle_objective) / max(oracle_objective, 1e-12),
                )
                save(row)
            # Oracle-label replay only: do not conflate this with online timing.
            for seed in seeds:
                learned_order, _ = model.rank(qc, device)
                random_order = np.random.default_rng(seed).permutation(len(CONFIGS)).tolist()
                heuristic_rows = [features(qc, device, c) for c in CONFIGS]
                heuristic_order = sorted(
                    range(len(CONFIGS)),
                    key=lambda i: (
                        heuristic_rows[i][13] * heuristic_rows[i][2]
                        - (heuristic_rows[i][17] * 2 if CONFIGS[i].rewrite else 0),
                        not CONFIGS[i].rewrite,
                        CONFIGS[i].routing != "lookahead",
                        i,
                    ),
                )
                for name, order in (
                    ("learned", learned_order),
                    ("random", random_order),
                    ("heuristic", heuristic_order),
                ):
                    for b in (1, 2, 4, 8, 12, 24):
                        objective = min(oracle_values[i] for i in order[:b])
                        replay_rows.append(
                            {
                                "circuit_id": spec["id"],
                                "seed": seed,
                                "method": name,
                                "budget": b,
                                "objective": objective,
                                "regret": (objective - oracle_objective) / max(oracle_objective, 1e-12),
                                "evidence": "offline replay of independently verified exhaustive labels; no online wall-time claim",
                            }
                        )
            for seed in seeds:
                baseline_zero = None
                for name in BASELINE_NAMES:
                    if name == "bqskit" and spec["id"] not in bq_subset:
                        continue
                    row, compiled = _external_row(qc, device, name, seed)
                    row.update(circuit_id=spec["id"], oracle_objective=oracle_objective)
                    if row["status"] == "ok":
                        row["regret"] = (row["metrics"]["objective"] - oracle_objective) / max(
                            oracle_objective, 1e-12
                        )
                    if name == "qiskit-0":
                        baseline_zero = compiled
                    save(row)
                if seed == seeds[0] and baseline_zero is not None:
                    try:
                        from .noise import compare_noise

                        best = native_best_by_seed[seed]
                        physical = qasm2.loads(
                            best["qasm"], custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS
                        )
                        physical.global_phase = best["global_phase"]
                        noise = compare_noise(
                            qc, (physical, best["final_mapping"]), baseline_zero, device, [], 0, seed
                        )
                        save(
                            {
                                "circuit_id": spec["id"],
                                "method": "noise-comparison",
                                "seed": seed,
                                "status": "noise-only",
                                "noise": noise,
                            }
                        )
                    except Exception as exc:
                        save(
                            {
                                "circuit_id": spec["id"],
                                "method": "noise-comparison",
                                "seed": seed,
                                "status": "noise-unavailable",
                                "reason": f"{type(exc).__name__}: {exc}",
                            }
                        )
            print(f"held-out instance {len(manifest)}: {spec['id']} complete, {len(rows)} rows", flush=True)
    finally:
        raw.close()
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "circuits": manifest,
                "training_hashes_disjoint": True,
                "bqskit_subset": sorted(bq_subset),
                "seeds": list(seeds),
                "budget": budget,
            },
            indent=2,
        )
        + "\n"
    )
    (output / "exhaustive.jsonl").write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in exhaustive_rows)
    )
    (output / "budget-replay.jsonl").write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in replay_rows)
    )
    summary = summarize(rows, manifest, budget, seeds)
    summary.update(
        training_circuits=model.data["training_circuits"],
        training_rows=model.data["training_rows"],
        model_sha256=model.sha256,
        graph_free_model_sha256=graph_free.sha256,
        training_label_source_sha256=model.data["training"].get("source_sha256"),
        benchmark_native_source_sha256=source_fingerprint(),
        source_note="Training label source digest is preserved. Final source includes validation hardening and standard-class gate construction, with the generated canonical gate semantics unchanged; all held-out outputs are freshly verified.",
        elapsed_s=perf_counter() - started,
        train_test_exact_hashes_disjoint=True,
        verified_native_evaluations=len(exhaustive_rows) + len(manifest) * len(seeds) * 5 * budget,
        environment={
            "python": platform.python_version(),
            "platform": platform.platform(),
            "versions": {
                name: version(name)
                for name in ("numpy", "qiskit", "qiskit-aer", "bqskit", "mqt.qmap", "scikit-learn")
            },
        },
        results_sha256=sha256((output / "results.jsonl").read_bytes()).hexdigest(),
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    data_path = Path(__file__).parent / "data" / "benchmarks.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(summary, indent=2) + "\n")
    return refresh_summary(output)


def refresh_summary(output: str | Path) -> dict[str, Any]:
    """Rebuild aggregation from immutable numerical rows, without rerunning compilers."""
    output = Path(output)
    rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines()]
    manifest = json.loads((output / "manifest.json").read_text())
    previous = json.loads((output / "summary.json").read_text())
    seeds = tuple(manifest["seeds"])
    summary = {**previous, **summarize(rows, manifest["circuits"], manifest["budget"], seeds)}
    strata = []
    for name, selected in (
        ("seen-topologies", [s for s in manifest["circuits"] if not s["heldout_topology"]]),
        ("heldout-star-topology", [s for s in manifest["circuits"] if s["heldout_topology"]]),
        ("seen-families", [s for s in manifest["circuits"] if not s["heldout_family"]]),
        ("heldout-families", [s for s in manifest["circuits"] if s["heldout_family"]]),
    ):
        ids = {s["id"] for s in selected}
        if selected:
            partial = summarize(
                [r for r in rows if r["circuit_id"] in ids], selected, manifest["budget"], seeds
            )
            strata.append(
                {
                    "name": name,
                    "circuit_device_instances": len(selected),
                    "unique_circuit_inputs": partial["unique_circuit_inputs"],
                    "methods": partial["methods"],
                    "paired_comparisons": partial["paired_comparisons"],
                }
            )
    summary["strata"] = strata
    summary["results_sha256"] = sha256((output / "results.jsonl").read_bytes()).hexdigest()
    import os

    summary.setdefault("environment", {}).update(machine=platform.machine(), logical_cpu_count=os.cpu_count())
    summary["uncertainty_note"] = (
        "Exact numerical input hashes define clusters; topology repeats and all requested seeds stay within cluster. Weighted cluster resampling preserves the case mean."
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (Path(__file__).parent / "data" / "benchmarks.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
