"""Optional real-compiler integration checks.

Run with QLOOM_TEST_OPTIONAL_BASELINES=1 pytest tests/test_baselines.py.
Core-only installations skip this module's tests without importing compilers.
"""

import os

import numpy as np
import pytest
from qiskit import QuantumCircuit

from qloom.baselines import compile_baseline
from qloom.devices import make_device
from qloom.examples import generate
from qloom.verify import logical_matrix, verify

pytestmark = pytest.mark.skipif(
    os.environ.get("QLOOM_TEST_OPTIONAL_BASELINES") != "1",
    reason="Optional external compilers: set QLOOM_TEST_OPTIONAL_BASELINES=1.",
)


def _restore_declared_phase_and_check(reference, physical, initial, final):
    identity = list(range(reference.num_qubits))
    u = logical_matrix(reference, identity, identity)
    v = logical_matrix(physical, initial, final)
    # QMAP may discard global phase; restore it explicitly and still require
    # the complete operator, including arbitrary inputs on unused wires.
    correction = -float(np.angle(np.vdot(u, v)))
    physical.global_phase += correction
    result = verify(reference, physical, initial, final)
    assert result["passed"], result
    assert result["max_error"] < 1e-8


@pytest.mark.parametrize(
    "topology,input_seed,expected_idle",
    [("ring", 10202, [2, 3]), ("star", 10204, [1])],
)
def test_qmap_original_idle_wire_numbers(topology, input_seed, expected_idle):
    pytest.importorskip("mqt.qmap")
    qc = generate("mirror", 5, input_seed, layers=2)
    qc.global_phase = 0.519
    out, initial, final, metadata = compile_baseline(qc, make_device(topology, 5), "qmap", 0)
    assert metadata["idle_wire_identity_markers"] == expected_idle
    _restore_declared_phase_and_check(qc, out, initial, final)
    assert all(
        inst.operation.name != "id"
        and not (inst.operation.name in {"u", "u3"} and all(float(p) == 0.0 for p in inst.operation.params))
        for inst in out.data
    )


@pytest.mark.parametrize("topology", ["line", "ring", "star"])
def test_qmap_sparse_input_preserves_arbitrary_idle_states(topology):
    pytest.importorskip("mqt.qmap")
    qc = QuantumCircuit(6)
    qc.global_phase = 0.123
    qc.ry(-0.73, 2)
    qc.cx(2, 5)
    qc.rz(0.37, 5)
    qc.cx(5, 3)
    qc.rx(0.19, 3)
    out, initial, final, metadata = compile_baseline(qc, make_device(topology, 6), "qmap", 0)
    assert metadata["idle_wire_identity_markers"] == [0, 1, 4]
    _restore_declared_phase_and_check(qc, out, initial, final)


@pytest.mark.parametrize("n", [2, 5])
def test_qmap_empty_unitary_retains_full_dimension(n):
    pytest.importorskip("mqt.qmap")
    qc = QuantumCircuit(n)
    qc.global_phase = 0.123
    out, initial, final, metadata = compile_baseline(qc, make_device("line", n), "qmap", 0)
    assert out.num_qubits == n
    assert not out.data
    assert metadata["idle_wire_identity_markers"] == list(range(n))
    _restore_declared_phase_and_check(qc, out, initial, final)


def test_optional_worker_timeout_reaps_its_process_group(monkeypatch):
    pytest.importorskip("bqskit")
    import qloom.baselines as baselines

    if os.name != "posix":
        pytest.skip("Process-group check is POSIX-specific.")
    monkeypatch.setenv("QLOOM_BASELINE_TIMEOUT", "1")
    original_popen = baselines.subprocess.Popen
    process_ids = []

    def capture_process(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        process_ids.append(process.pid)
        return process

    monkeypatch.setattr(baselines.subprocess, "Popen", capture_process)
    qc = generate("ghz", 3, 0)
    with pytest.raises(TimeoutError, match="worker group terminated"):
        compile_baseline(qc, make_device("line", 3), "bqskit", 0)
    assert len(process_ids) == 1
    with pytest.raises(ProcessLookupError):
        os.killpg(process_ids[0], 0)
