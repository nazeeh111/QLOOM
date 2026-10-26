"""Explicit external compiler baselines; never used by QLOOM's native router.

Adapters return physical circuits and logical-to-physical permutations. They
do not assert equivalence or silently align global phase. The caller must run
the same independent verifier used for native candidates.
"""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from qiskit import QuantumCircuit, qasm2, transpile
from qiskit.transpiler import CouplingMap


class DeviceLike(Protocol):
    n_qubits: int
    edges: list[tuple[int, int]]


BASELINE_NAMES = ("qiskit-0", "qiskit-1", "qiskit-2", "qiskit-3", "qmap", "bqskit")


def _terminate_worker(process: subprocess.Popen[str]) -> None:
    """Terminate the isolated worker and its POSIX descendants, then reap it."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.communicate()


def _layout(circuit: QuantumCircuit, n: int) -> tuple[list[int], list[int]]:
    if circuit.layout is None:
        return list(range(n)), list(range(n))
    initial = list(circuit.layout.initial_index_layout(filter_ancillas=True))[:n]
    if circuit.layout.final_layout is None:
        return initial, initial.copy()
    # Compose using physical circuit wire order. mqt-core 3.11 constructs its
    # TranspileLayout output list in dictionary insertion order, which can
    # differ from physical wire order and makes final_index_layout incorrect.
    final = [circuit.layout.final_layout[circuit.qubits[p]] for p in initial]
    return initial, final


def compile_baseline(
    qc: QuantumCircuit,
    device: DeviceLike,
    name: str,
    seed: int = 0,
) -> tuple[QuantumCircuit, list[int], list[int], dict[str, Any]]:
    """Run an external baseline, isolating QMAP/BQSKit behind a hard timeout.

    ``QLOOM_BASELINE_TIMEOUT`` controls wall time including worker startup and
    imports, defaults to 45 seconds, and must be in [1, 300]. Timeouts are
    failures, never fabricated candidates. On POSIX, the worker's complete
    process group is killed so BQSKit's local runtime does not outlive the job.
    Qiskit levels execute in process. Transport preserves declared global phase;
    any compiler phase discrepancy still requires the independent verifier.
    """
    if name not in {"qmap", "bqskit"}:
        return _compile_baseline_direct(qc, device, name, seed)
    try:
        timeout_s = float(os.environ.get("QLOOM_BASELINE_TIMEOUT", "45"))
    except ValueError as exc:
        raise ValueError("QLOOM_BASELINE_TIMEOUT must be a number in [1, 300] seconds.") from exc
    if not math.isfinite(timeout_s) or not 1 <= timeout_s <= 300:
        raise ValueError("QLOOM_BASELINE_TIMEOUT must be a number in [1, 300] seconds.")
    started = perf_counter()
    request = {
        "qasm": qasm2.dumps(qc),
        "global_phase": float(qc.global_phase),
        "device": {"n_qubits": int(device.n_qubits), "edges": list(device.edges)},
        "name": name,
        "seed": int(seed),
    }
    env = os.environ.copy()
    # Also works when invoked directly from a source checkout using sys.path.
    source_root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.Popen(
        [sys.executable, "-m", "qloom.baseline_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = process.communicate(json.dumps(request), timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        _terminate_worker(process)
        elapsed = perf_counter() - started
        raise TimeoutError(
            f"{name} exceeded {timeout_s:g}s wall-time limit; worker group terminated "
            f"after {elapsed:.3f}s (including imports/startup)."
        ) from exc
    except BaseException:
        _terminate_worker(process)
        raise
    elapsed = perf_counter() - started
    if process.returncode:
        detail = stderr.strip().splitlines()[-1] if stderr.strip() else "worker returned no diagnostic"
        raise RuntimeError(f"{name} worker failed after {elapsed:.3f}s: {detail[:500]}")
    try:
        response = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"{name} worker produced invalid output after {elapsed:.3f}s.") from exc
    if "error" in response:
        raise RuntimeError(f"{name} failed after {elapsed:.3f}s: {response['error'][:500]}")
    out = qasm2.loads(response["qasm"], custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
    out.global_phase = float(response["global_phase"])
    metadata = response["metadata"]
    metadata["worker_compile_elapsed_s"] = metadata["elapsed_s"]
    metadata["elapsed_s"] = perf_counter() - started
    metadata["timeout_s"] = timeout_s
    metadata["timing_scope"] = "wall time including isolated worker imports/startup and QASM transport"
    return out, response["initial"], response["final"], metadata


def _compile_baseline_direct(
    qc: QuantumCircuit,
    device: DeviceLike,
    name: str,
    seed: int = 0,
) -> tuple[QuantumCircuit, list[int], list[int], dict[str, Any]]:
    """Compile a unitary circuit at equal physical width in the CX/U3 basis.

    ``qmap`` is its heuristic superconducting mapper, not the exponential exact
    mapper. ``bqskit`` uses level 1 and two-qubit synthesis blocks on one worker.
    Optional-import and compiler failures propagate to the experiment runner,
    where they must be recorded as failed/unavailable rows rather than wins.
    QMAP does not expose a random-seed argument, which is recorded explicitly.
    """
    if name not in BASELINE_NAMES:
        raise ValueError(f"Unknown baseline {name!r}; choose from {BASELINE_NAMES}.")
    if qc.num_qubits != device.n_qubits:
        raise ValueError("Baselines require input width equal to device width; no ancillas.")
    if qc.num_clbits or any(i.operation.name in {"measure", "reset"} for i in qc.data):
        raise ValueError("Baseline adapter expects the unitary prefix; restore measurements separately.")
    edges = sorted({(int(u), int(v)) for u, v in device.edges for u, v in [(u, v), (v, u)]})
    coupling = CouplingMap(edges) if edges else None
    started = perf_counter()
    metadata: dict[str, Any] = {
        "name": name,
        "requested_seed": int(seed),
        "basis_gates": ["u", "cx"],
        "physical_qubits": device.n_qubits,
        "phase_alignment": "none; independent verifier must check phase",
        "budget_note": "One external compiler invocation; compare measured wall time separately.",
        "timing_scope": "in-process compiler call including optional dependency imports",
    }

    if name.startswith("qiskit-"):
        level = int(name.rsplit("-", 1)[1])
        out = transpile(
            qc,
            basis_gates=["u", "cx"],
            coupling_map=coupling,
            optimization_level=level,
            seed_transpiler=seed,
        )
        initial, final = _layout(out, qc.num_qubits)
        metadata.update(version=version("qiskit"), optimization_level=level)
    elif name == "qmap":
        from mqt.qmap.plugins.qiskit.sc import compile_
        from mqt.qmap.sc import Architecture, Method

        # QMAP maps a gate-level circuit; use only basis translation, with no
        # placement/routing/optimization before the mapper sees the input.
        lowered = transpile(qc, basis_gates=["u", "cx"], optimization_level=0)
        # QMAP 3.11 unconditionally strips idle source wires in its Mapper
        # constructor. Their removal compacts logical labels, so layouts can
        # refer to compressed logical indices rather than original wires.
        # Explicit exact identities retain the full logical wire numbering.
        touched = {
            lowered.find_bit(qubit).index
            for instruction in lowered.data
            if instruction.operation.name != "barrier"
            for qubit in instruction.qubits
        }
        idle_markers = [i for i in range(qc.num_qubits) if i not in touched]
        for qubit in idle_markers:
            lowered.u(0.0, 0.0, 0.0, qubit)
        out, result = compile_(
            lowered,
            Architecture(device.n_qubits, set(edges)),
            method=Method.heuristic,
            add_measurements_to_mapped_circuit=False,
        )
        initial, final = _layout(out, qc.num_qubits)
        # QMAP may return explicit SWAPs or standard one-qubit gates. Preserve
        # the recorded placement before translating only to the common basis.
        out = transpile(out, basis_gates=["u", "cx"], optimization_level=0)
        # Markers have no physical cost. Remove only algebraically exact
        # identities, never a small-angle or broad numerical approximation.
        retained = out.copy_empty_like()
        removed_identities = 0
        for instruction in out.data:
            gate = instruction.operation
            if gate.name == "id" or (
                gate.name in {"u", "u3"}
                and len(gate.params) == 3
                and all(float(p) == 0.0 for p in gate.params)
            ):
                removed_identities += 1
            else:
                retained.append(instruction)
        out = retained
        metadata.update(
            version=version("mqt.qmap"),
            method="heuristic",
            seed_supported=False,
            qmap=result.json(),
            layout_extraction="initial permutation composed with final layout in physical wire order",
            phase_alignment="none; QMAP conversion may discard global phase; verifier must report it",
            idle_wire_identity_markers=idle_markers,
            exact_identity_operations_removed=removed_identities,
        )
    else:
        from bqskit import MachineModel
        from bqskit import compile as bcompile
        from bqskit.ext.qiskit import bqskit_to_qiskit, qiskit_to_bqskit
        from bqskit.ir.gates import CNOTGate, U3Gate

        model = MachineModel(
            device.n_qubits,
            coupling_graph=sorted({tuple(sorted(edge)) for edge in edges}),
            gate_set={CNOTGate(), U3Gate()},
        )
        compiled, initial_tuple, final_tuple = bcompile(
            qiskit_to_bqskit(qc),
            model,
            optimization_level=1,
            max_synthesis_size=2,
            synthesis_epsilon=1e-10,
            seed=seed,
            with_mapping=True,
            num_workers=1,
        )
        initial, final = list(initial_tuple), list(final_tuple)
        out = bqskit_to_qiskit(compiled)
        out = transpile(out, basis_gates=["u", "cx"], optimization_level=0)
        metadata.update(
            version=version("bqskit"),
            optimization_level=1,
            max_synthesis_size=2,
            synthesis_epsilon=1e-10,
            num_workers=1,
            phase_alignment="none; numerical synthesis may return a global phase difference",
        )

    metadata["elapsed_s"] = perf_counter() - started
    return out, initial, final, metadata
