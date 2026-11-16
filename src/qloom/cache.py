"""Version-bound local report cache; cached numerical claims are rechecked.

Checksums detect accidental corruption, not malicious re-signing. Noise and
historical timings are retained observations, not newly executed experiments.
"""

import json
import os
import platform
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import NamedTemporaryFile

from .candidates import revalidate_candidate
from .circuits import circuit_identity, serialize_input, split_circuit
from .cost import pareto
from .report_policy import (EXPORT_NOTE, NOISE_ASSUMPTIONS, NOISE_LIMIT, NOISE_METHOD,
                            NOISE_NOT_RUN, NOISE_UNAVAILABLE, baseline_names, baseline_tolerance)
from .routing import CONFIGS

CACHE_SCHEMA = 1
MAX_CACHE_BYTES = 64 * 1024 * 1024


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def implementation_identity():
    """Bind all package code and relevant installed numerical/adapter versions."""
    packages = {}
    for name in ("numpy", "qiskit", "qiskit-aer", "mqt.qmap", "bqskit"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "source": {
            p.name: sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        },
        "packages": packages,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "baseline_timeout": os.environ.get("QLOOM_BASELINE_TIMEOUT", "45"),
    }


def request_identity(qc, device, budget, seed, strategy, model, baselines, noisy, graph_aware):
    request = {
        "cache_schema": CACHE_SCHEMA,
        "implementation": implementation_identity(),
        "input": circuit_identity(qc),
        "device": device.to_dict(),
        "budget": budget,
        "seed": seed,
        "strategy": strategy,
        "model": model.sha256 if model else None,
        "model_metadata": model.metadata() if model else {"name": strategy},
        "baselines": baselines,
        "noisy": noisy,
        "graph_aware": graph_aware,
    }
    # Device dataclasses contain tuples; compare their on-disk JSON representation.
    return json.loads(json.dumps(request, allow_nan=False))


def validate_report(report, request, qc, device):
    if not isinstance(report, dict) or report["schema_version"] != "1.0":
        raise ValueError("Unsupported cached report schema.")
    for key in ("seed", "strategy", "budget", "device"):
        if report[key] != request[key]:
            raise ValueError(f"Cached {key} does not match the request.")
    if {key: report["input"][key] for key in request["input"]} != request["input"]:
        raise ValueError("Cached input identity mismatch.")
    if report["model"] != request["model_metadata"]:
        raise ValueError("Cached model metadata mismatch.")
    for key in ("search_time_s", "optimizer_time_s", "elapsed_s"):
        if not isinstance(report[key], (int, float)) or report[key] < 0:
            raise ValueError("Invalid cached generation time.")
    if report["export_note"] != EXPORT_NOTE:
        raise ValueError("Cached export semantics mismatch.")
    candidates = report["candidates"]
    if not isinstance(candidates, list) or len(candidates) != request["budget"]:
        raise ValueError("Cached candidate count does not match budget.")
    reference, measurements = split_circuit(qc)
    identifiers = set()
    configs = {f"qloom-{i:02d}": c.to_dict() for i, c in enumerate(CONFIGS)}
    for c in candidates:
        if c["id"] in identifiers or c["config"] != configs[c["id"]]:
            raise ValueError("Cached candidate configuration mismatch.")
        identifiers.add(c["id"])
        _validate_metadata(c)
        revalidate_candidate(c, reference, device, measurements, qc.num_clbits, request["seed"])
    best = min(candidates, key=lambda c: (c["metrics"]["objective"], c["id"]))
    if report["best_id"] != best["id"] or report["pareto_ids"] != pareto(candidates):
        raise ValueError("Cached selection disagrees with verified candidate costs.")
    expected = baseline_names(request["baselines"], request["noisy"])
    if not isinstance(report["baselines"], list) or [b["id"] for b in report["baselines"]] != expected:
        raise ValueError("Cached baseline coverage mismatch.")
    for baseline in report["baselines"]:
        if baseline["status"] == "ok":
            _validate_metadata(baseline)
            revalidate_candidate(
                baseline, reference, device, measurements, qc.num_clbits, request["seed"],
                baseline_tolerance(baseline["id"]),
            )
        elif baseline["status"] != "unavailable-or-failed" or not isinstance(baseline["reason"], str):
            raise ValueError("Invalid cached baseline status.")
    validate_noise(report["noise"], request, reference, measurements, qc.num_clbits, report["baselines"])
    # Names/register labels belong to the current caller, not the original writer.
    report["input"] = serialize_input(qc)


def validate_noise(noise, request, reference, measurements, n_clbits, baselines):
    """Check historical observations for shape and internal consistency, not provenance."""
    import math
    import numpy as np
    from .circuits import operations
    from .noise import distribution_fidelity
    from .verify import classical_probabilities, evolve

    baseline_ok = any(b["id"] == "qiskit-0" and b["status"] == "ok" for b in baselines)
    if not request["noisy"] or not baseline_ok:
        expected = {"method": "not-run", "assumptions": NOISE_NOT_RUN}
    elif reference.num_qubits > 6:
        expected = {"method": "not-run", "assumptions": NOISE_LIMIT}
    elif noise == {"method": "unavailable", "assumptions": NOISE_UNAVAILABLE}:
        return
    else:
        expected = None
    if expected is not None:
        if noise != expected:
            raise ValueError("Cached noise status disagrees with request or baseline.")
        return
    keys = {"method", "assumptions", "ideal_probabilities", "optimized_probabilities",
            "input_probabilities", "optimized_fidelity", "input_fidelity"}
    if not isinstance(noise, dict) or set(noise) != keys or noise["method"] != NOISE_METHOD or noise["assumptions"] != NOISE_ASSUMPTIONS:
        raise ValueError("Invalid cached noise observation schema.")
    size = 1 << (n_clbits if measurements else reference.num_qubits)
    arrays = []
    for key in ("ideal_probabilities", "optimized_probabilities", "input_probabilities"):
        values = noise[key]
        if (not isinstance(values, list) or len(values) != size or
            any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v > 1 for v in values) or
            not math.isclose(sum(values), 1.0, abs_tol=1e-8)):
            raise ValueError("Invalid cached noise probability distribution.")
        arrays.append(np.asarray(values))
    zero = np.zeros(1 << reference.num_qubits, complex)
    zero[0] = 1
    ideal = classical_probabilities(abs(evolve(operations(reference), reference.num_qubits, zero,
                                             float(reference.global_phase))) ** 2,
                                    measurements, n_clbits)
    if not np.allclose(arrays[0], ideal, rtol=0, atol=1e-8):
        raise ValueError("Cached ideal distribution disagrees with input circuit.")
    for key, values in (("optimized_fidelity", arrays[1]), ("input_fidelity", arrays[2])):
        value = noise[key]
        if (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1 or
            not math.isclose(value, distribution_fidelity(arrays[0], values), abs_tol=1e-8)):
            raise ValueError("Cached noise fidelity disagrees with distributions.")


def _validate_metadata(candidate):
    if not isinstance(candidate["history"], list) or not all(
        isinstance(event, dict) for event in candidate["history"]
    ):
        raise ValueError("Invalid cached history.")
    for value in (candidate["elapsed_s"], candidate["metrics"]["compile_time_s"]):
        if type(value) not in (int, float) or value < 0:
            raise ValueError("Invalid cached candidate time.")
    if candidate["model_prediction"] is not None and type(candidate["model_prediction"]) not in (int, float):
        raise ValueError("Invalid cached model prediction.")


def read_report(path, request, qc, device):
    """Return (verified report, diagnostic); every invalid entry is a miss."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CACHE_BYTES + 1)
        if len(raw) > MAX_CACHE_BYTES:
            raise ValueError("Cache entry exceeds 64 MiB.")
        entry = json.loads(raw)
        if entry["schema"] != CACHE_SCHEMA or entry["request"] != request:
            raise ValueError("Cache schema or request identity mismatch.")
        report = entry["report"]
        if entry["report_sha256"] != digest(report):
            raise ValueError("Cache report checksum mismatch.")
        validate_report(report, request, qc, device)
        return report, {"status": "verified-hit"}
    except FileNotFoundError:
        return None, {"status": "miss"}
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, RecursionError) as exc:
        return None, {"status": "rejected", "reason": f"{type(exc).__name__}: {exc}"}


def write_report(path, request, report):
    """Publish one complete generation, with no shared temporary filename."""
    entry = {"schema": CACHE_SCHEMA, "request": request, "report": report, "report_sha256": digest(report)}
    payload = json.dumps(entry, indent=2, allow_nan=False)
    if len(payload.encode()) > MAX_CACHE_BYTES:
        raise ValueError("Cache entry exceeds 64 MiB.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=f".{path.stem}.", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(payload)
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
