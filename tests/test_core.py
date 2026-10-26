import numpy as np
import pytest
from qiskit import QuantumCircuit

from qloom.circuits import export_qasm, load_qasm, operations, split_circuit
from qloom.cost import metrics
from qloom.devices import Device, make_device
from qloom.examples import example_list, generate
from qloom.routing import CONFIGS, native_compile, rewrite_ops
from qloom.verify import classical_probabilities, evolve, verify


@pytest.mark.parametrize("family", ["random", "mirror", "qaoa", "qft", "starphase", "ghz"])
@pytest.mark.parametrize("topology", ["line", "ring", "star", "grid"])
def test_native_semantics_and_constraints(family, topology):
    reference = generate(family, 4, 37, 2)
    reference.global_phase = 0.371
    device = make_device(topology, 4)
    for config in CONFIGS:
        out, initial, final, _ = native_compile(reference, device, config)
        assert verify(reference, out, initial, final)["passed"]
        assert metrics(out, device)["estimated_success"] <= 1


def test_verifier_detects_wrong_mapping_phase_and_gate():
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 2)
    qc.ry(0.31, 1)
    out, initial, final, _ = native_compile(qc, make_device("line", 3), CONFIGS[-1])
    assert verify(qc, out, initial, final)["passed"]
    corrupted = out.copy()
    corrupted.global_phase += 0.13
    assert not verify(qc, corrupted, initial, final)["passed"]
    corrupted = out.copy()
    corrupted.x(1)
    assert not verify(qc, corrupted, initial, final)["passed"]
    wrong = final.copy()
    wrong[0], wrong[1] = wrong[1], wrong[0]
    assert not verify(qc, out, initial, wrong)["passed"]


def test_independent_interpreter_crosschecks_qiskit_reference():
    from qiskit.quantum_info import Operator

    for family in ["random", "qft", "starphase", "mirror"]:
        qc = generate(family, 3, 51, 3)
        qc.global_phase = 0.93
        ours = evolve(operations(qc), 3, np.eye(8, dtype=complex), float(qc.global_phase))
        assert np.max(np.abs(ours - Operator(qc).data)) < 1e-12


def test_measurement_export_preserves_classical_order():
    qc = generate("random", 4, 3, 2, measured=True)
    reference, measurements = split_circuit(qc)
    out, initial, final, _ = native_compile(reference, make_device("line", 4), CONFIGS[-1])
    exported = load_qasm(export_qasm(out, measurements, final, 4))
    physical_measures = [
        (exported.find_bit(i.qubits[0]).index, exported.find_bit(i.clbits[0]).index)
        for i in exported.data
        if i.operation.name == "measure"
    ]
    assert physical_measures == [(final[q], c) for q, c in measurements]
    rng = np.random.default_rng(3)
    p = rng.random(16)
    p /= p.sum()
    cp = classical_probabilities(p, measurements, 4)
    for x, prob in enumerate(p):
        reversed_bits = int(f"{x:04b}"[::-1], 2)
        assert cp[reversed_bits] == prob


@pytest.mark.parametrize(
    "source",
    [
        "OPENQASM 3.0; qubit[2] q;",
        'OPENQASM 2.0; include "/etc/passwd"; qreg q[2];',
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; reset q[0];',
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; measure q[0]->c[0]; x q[1];',
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; measure q[0]->c[0]; measure q[1]->c[0];',
    ],
)
def test_unsupported_rejected(source):
    with pytest.raises(ValueError):
        load_qasm(source)


def test_native_rewrite_retains_two_pi_phase():
    qc = QuantumCircuit(2)
    qc.rx(np.pi, 0)
    qc.rx(np.pi, 0)
    ops, edits = rewrite_ops(operations(qc))
    assert edits == 1 and ops[0]["params"][0] == 2 * np.pi
    out, initial, final, _ = native_compile(qc, make_device("line", 2), CONFIGS[-1])
    assert verify(qc, out, initial, final)["passed"]


def test_invalid_device_and_width():
    with pytest.raises(ValueError):
        Device("bad", 3, ((0, 1),))
    with pytest.raises(ValueError):
        make_device("line", 3, two_error=float("nan"))
    with pytest.raises(ValueError):
        native_compile(QuantumCircuit(3), make_device("line", 4), CONFIGS[0])


def test_examples_parse():
    for item in example_list():
        assert load_qasm(item["qasm"]).num_qubits == 5
