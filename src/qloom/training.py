"""Reproducible offline labels from real native compiler evaluations.

No target circuit or held-out topology enters the fit. ExtraTrees is optional at
inference: the trained ensemble is exported to explicit JSON arrays.
"""

from __future__ import annotations

import json
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from qiskit import QuantumCircuit, qasm2

from .cost import metrics
from .devices import make_device
from .examples import generate
from .features import FEATURE_NAMES, features
from .routing import CONFIGS, native_compile
from .surrogate import export_forest
from .verify import verify

TRAINING_FAMILIES = ("random", "mirror", "qaoa")
TRAINING_TOPOLOGIES = ("line", "ring", "grid")


def source_fingerprint() -> str:
    root = Path(__file__).parent
    return sha256(
        b"".join(
            (root / name).read_bytes()
            for name in ("training.py", "routing.py", "features.py", "verify.py", "cost.py", "examples.py")
        )
    ).hexdigest()


def circuit_fingerprint(qc: QuantumCircuit) -> str:
    # QASM name/comments do not affect semantics; generated numerical gate text
    # plus global phase determine this reproducible exact-input split key.
    return sha256((qasm2.dumps(qc) + repr(float(qc.global_phase))).encode()).hexdigest()


def training_specs(count: int = 120, seed: int = 20261025):
    """Unique seeded numerical circuits, with no star-topology training labels."""
    rng = np.random.default_rng(seed)
    for index in range(count):
        family = TRAINING_FAMILIES[index % len(TRAINING_FAMILIES)]
        n = 3 + ((index // 3) % 4)
        topology = TRAINING_TOPOLOGIES[(index // 12) % len(TRAINING_TOPOLOGIES)]
        circuit_seed = int(rng.integers(1, 2**31))
        layers = 2 + ((index // 36) % 3)
        base = generate(family, n, circuit_seed, layers)
        # GHZ/QAOA alone do not vary with the seed. These explicit, seeded input
        # rotations make exact circuit instances unique without changing labels.
        qc = QuantumCircuit(n, name=f"train-{family}-{index:03d}")
        for q in range(n):
            qc.ry(float(rng.uniform(-np.pi, np.pi)), q)
        qc.compose(base, inplace=True)
        qc.global_phase = float(rng.uniform(-np.pi, np.pi))
        yield (
            {
                "id": f"train-{index:03d}",
                "family": family,
                "n_qubits": n,
                "topology": topology,
                "seed": circuit_seed,
                "layers": layers,
            },
            qc,
        )


def train(
    output_dir: str | Path, count: int = 120, seed: int = 20261025, model_path: str | Path | None = None
) -> dict[str, Any]:
    """Evaluate all 24 configurations on each training instance, then fit."""
    from sklearn.ensemble import ExtraTreesRegressor

    if count < 12:
        raise ValueError("Use at least 12 training circuits for a reproducible fit.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    rows, manifest, seen_hashes = [], [], set()
    targets, feature_rows = [], []
    raw_path = output / "training-evaluations.jsonl"
    with raw_path.open("w") as raw:
        for spec, qc in training_specs(count, seed):
            fingerprint = circuit_fingerprint(qc)
            if fingerprint in seen_hashes:
                raise RuntimeError("Duplicate exact training circuit; split is invalid.")
            seen_hashes.add(fingerprint)
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
            two_count = sum(len(inst.qubits) == 2 for inst in qc.data)
            normalizer = two_count + 1
            for index, config in enumerate(CONFIGS):
                t = perf_counter()
                physical, initial, final, _ = native_compile(qc, device, config)
                compile_s = perf_counter() - t
                verification = verify(qc, physical, initial, final, seed)
                if not verification["passed"]:
                    raise RuntimeError(f"Training semantics failed: {spec['id']}/{index}: {verification}")
                result = metrics(physical, device, compile_s)
                row_features = features(qc, device, config)
                target = result["objective"] / normalizer
                row = {
                    "circuit_id": spec["id"],
                    "circuit_sha256": fingerprint,
                    "config_id": index,
                    "config": config.to_dict(),
                    "features": row_features,
                    "target": target,
                    "normalizer": normalizer,
                    "metrics": result,
                    "verification": verification,
                }
                raw.write(json.dumps(row, separators=(",", ":")) + "\n")
                rows.append(row)
                feature_rows.append(row_features)
                targets.append(target)
            raw.flush()
            if (len(manifest) % 12) == 0:
                print(
                    f"training labels: {len(manifest)}/{count} circuits, {len(rows)} verified compilations",
                    flush=True,
                )
    estimator = ExtraTreesRegressor(
        n_estimators=48, max_depth=10, min_samples_leaf=3, max_features=1.0, random_state=seed, n_jobs=1
    )
    estimator.fit(np.asarray(feature_rows), np.asarray(targets))
    metadata = {
        "training_rows": len(rows),
        "training_circuits": len(manifest),
        "training": {
            "seed": seed,
            "families": list(TRAINING_FAMILIES),
            "topologies": list(TRAINING_TOPOLOGIES),
            "qubits": [3, 4, 5, 6],
            "label": "objective / (input two-qubit gates + 1)",
            "source_sha256": source_fingerprint(),
            "raw_labels_sha256": sha256(raw_path.read_bytes()).hexdigest(),
            "model_type": "ExtraTreesRegressor",
            "trees": 48,
            "max_depth": 10,
            "min_samples_leaf": 3,
            "feature_names": FEATURE_NAMES,
            "versions": {name: version(name) for name in ("qiskit", "numpy", "scikit-learn")},
        },
    }
    target_path = Path(model_path) if model_path else Path(__file__).parent / "data" / "surrogate.json"
    export_forest(estimator, metadata, target_path)
    model_copy = output / "surrogate.json"
    model_copy.write_bytes(target_path.read_bytes())
    metadata["model_sha256"] = sha256(target_path.read_bytes()).hexdigest()
    metadata["elapsed_s"] = perf_counter() - started
    metadata["training_r2_in_sample_not_generalization"] = float(estimator.score(feature_rows, targets))
    (output / "training-manifest.json").write_text(
        json.dumps({"metadata": metadata, "circuits": manifest}, indent=2) + "\n"
    )
    (output / "training-summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def train_graph_free(
    output_dir: str | Path, seed: int = 20261025, model_path: str | Path | None = None
) -> dict[str, Any]:
    """Refit the same estimator with all 13 graph summaries removed.

    This is a genuine retrained feature ablation, rather than an inference-only
    out-of-distribution masking experiment. Non-graph counts/config flags remain.
    """
    from sklearn.ensemble import ExtraTreesRegressor

    output = Path(output_dir)
    rows = [json.loads(line) for line in (output / "training-evaluations.jsonl").read_text().splitlines()]
    x = np.asarray([r["features"] for r in rows])
    x[:, 4:17] = 0.0
    y = np.asarray([r["target"] for r in rows])
    estimator = ExtraTreesRegressor(
        n_estimators=48, max_depth=10, min_samples_leaf=3, max_features=1.0, random_state=seed, n_jobs=1
    )
    estimator.fit(x, y)
    primary = json.loads((output / "training-summary.json").read_text())
    metadata = {
        "training_rows": len(rows),
        "training_circuits": primary["training_circuits"],
        "training": {
            **primary["training"],
            "ablation": "retrained without 13 interaction/hardware/placement graph summaries",
        },
    }
    target = Path(model_path) if model_path else Path(__file__).parent / "data" / "surrogate-no-graph.json"
    export_forest(estimator, metadata, target)
    (output / "surrogate-no-graph.json").write_bytes(target.read_bytes())
    return {"model_sha256": sha256(target.read_bytes()).hexdigest(), "training_rows": len(rows)}


def train_model(output: str | Path, quick: bool = False) -> dict[str, Any]:
    target = Path(output)
    artifact_dir = target.parent if target.suffix == ".json" else target
    model_path = target if target.suffix == ".json" else artifact_dir / "surrogate.json"
    result = train(artifact_dir, count=36 if quick else 120, model_path=model_path)
    result["graph_free_ablation"] = train_graph_free(
        artifact_dir, model_path=artifact_dir / "surrogate-no-graph.json"
    )
    return result
