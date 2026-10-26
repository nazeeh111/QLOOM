"""Independent semantic oracles and hostile-input regression checks."""

import numpy as np
import pytest
from qiskit import QuantumCircuit, qasm2
from qiskit.quantum_info import Operator

from qloom.circuits import export_qasm, load_qasm, split_circuit, validate
from qloom.compiler import compile_circuit
from qloom.devices import make_device
from qloom.routing import CONFIGS, native_compile
from qloom.verify import logical_matrix, verify


def oracle_logical_matrix(circuit, initial, final):
    """Use Qiskit's actual instruction definitions, independent of name dispatch."""
    n = circuit.num_qubits
    pin = [sum(((x >> q) & 1) << p for q, p in enumerate(initial)) for x in range(1 << n)]
    pout = [sum(((x >> q) & 1) << p for q, p in enumerate(final)) for x in range(1 << n)]
    return Operator(circuit).data[np.ix_(pout, pin)]


@pytest.mark.parametrize("topology", ["line", "star", "ring", "grid"])
def test_actual_operator_preserved_for_all_native_configurations(topology):
    rng = np.random.default_rng(710)
    circuit = QuantumCircuit(5)
    circuit.global_phase = 1.137
    for _ in range(16):
        a, b = rng.choice(5, 2, replace=False).tolist()
        circuit.u(*rng.uniform(-8, 8, 3), a)
        circuit.cx(a, b)
    circuit.rx(np.pi, 4)
    circuit.rx(np.pi, 4)
    circuit.p(0.773, 3)
    circuit.swap(0, 4)
    expected = Operator(circuit).data
    device = make_device(topology, 5)
    for config in CONFIGS:
        physical, initial, final, _ = native_compile(circuit, device, config)
        actual = oracle_logical_matrix(physical, initial, final)
        np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0)


def test_interpreter_on_all_standard_gate_types():
    # Legacy aliases are loaded by Qiskit to native standard instruction classes.
    circuit = qasm2.loads(
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[3]; '
        "id q[0]; h q[1]; x q[2]; y q[0]; z q[1]; "
        "s q[2]; sdg q[0]; t q[1]; tdg q[2]; "
        "rx(0.19) q[0]; ry(-0.71) q[1]; rz(6.7) q[2]; "
        "u1(0.2) q[0]; u2(0.3,-0.9) q[1]; u3(1.1,-2.1,0.4) q[2]; "
        "cx q[2],q[0]; cz q[1],q[2]; swap q[0],q[1];",
        custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS,
    )
    circuit.p(0.332, 0)
    circuit.u(0.1, -0.4, 0.6, 2)
    circuit.global_phase = 0.838
    np.testing.assert_allclose(
        logical_matrix(circuit, [0, 1, 2], [0, 1, 2]),
        Operator(circuit).data,
        atol=1e-12,
        rtol=0,
    )


@pytest.mark.parametrize("gate,params", [("u1", ".73"), ("u2", ".73,-.2"), ("u3", ".73,-.2,1.8")])
def test_supported_legacy_gate_aliases_compile(gate, params):
    circuit = load_qasm(f'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; {gate}({params}) q[0];')
    physical, initial, final, _ = native_compile(circuit, make_device("line", 2), CONFIGS[-1])
    np.testing.assert_allclose(
        oracle_logical_matrix(physical, initial, final),
        Operator(circuit).data,
        atol=1e-12,
        rtol=0,
    )


def test_custom_instruction_with_standard_name_is_rejected():
    body = QuantumCircuit(1)
    body.x(0)
    custom = body.to_gate()
    custom.name = "h"
    circuit = QuantumCircuit(2)
    circuit.append(custom, [0])
    with pytest.raises(ValueError):
        validate(circuit)


def test_verifier_itself_does_not_certify_name_spoofed_physical_gates():
    reference = QuantumCircuit(2)
    reference.h(0)
    body = QuantumCircuit(1)
    body.x(0)
    custom = body.to_gate()
    custom.name = "h"
    physical = QuantumCircuit(2)
    physical.append(custom, [0])
    assert np.max(np.abs(Operator(reference).data - Operator(physical).data)) > 0.7
    try:
        result = verify(reference, physical, [0, 1], [0, 1])
    except ValueError:
        return
    assert not result["passed"]


@pytest.mark.parametrize(
    "declaration",
    [
        "gate h q { U(pi,0,pi) q; }",
        "gate privategate q { U(pi,0,pi) q; }",
        "opaque h q;",
    ],
)
def test_custom_qasm_declarations_are_rejected(declaration):
    name = "privategate" if "privategate" in declaration else "h"
    source = f"OPENQASM 2.0; {declaration} qreg q[2]; {name} q[0];"
    with pytest.raises(ValueError):
        load_qasm(source)


@pytest.mark.parametrize(
    "declarations",
    [
        "qreg q[1000000000];",
        "qreg q[2]; creg c[1000000000];",
        "qreg a[5]; qreg b[5];",
        "qreg q[2]; creg a[10]; creg b[10];",
    ],
)
def test_register_bounds_checked_before_untrusted_parser_allocation(monkeypatch, declarations):
    def must_not_parse(*args, **kwargs):
        pytest.fail("Oversized registers reached the allocating QASM parser")

    monkeypatch.setattr(qasm2, "loads", must_not_parse)
    with pytest.raises(ValueError):
        load_qasm("OPENQASM 2.0; " + declarations)


def test_oversize_qasm_text_rejected_before_parsing(monkeypatch):
    def must_not_parse(*args, **kwargs):
        pytest.fail("Oversized text reached parser")

    monkeypatch.setattr(qasm2, "loads", must_not_parse)
    with pytest.raises(ValueError):
        load_qasm("OPENQASM 2.0; qreg q[2]; //" + "x" * 100001)


@pytest.mark.parametrize(
    "source",
    [
        'OPENQASM 2.0; include "../qelib1.inc"; qreg q[2];',
        'OPENQASM 2.0; include "/etc/passwd"; qreg q[2];',
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[1]; if(c==0) x q[0];',
        'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[1]; measure q[0]->c[0]; h q[1];',
    ],
)
def test_unsafe_or_unsupported_qasm_is_rejected(source):
    with pytest.raises(ValueError):
        load_qasm(source)


def test_measured_export_sparse_classical_order_and_json_phase_disclosure():
    circuit = QuantumCircuit(4, 7)
    circuit.x(0)
    circuit.ry(0.913, 3)
    circuit.cx(3, 1)
    circuit.cx(0, 3)
    circuit.global_phase = 0.747
    circuit.measure(3, 1)
    circuit.measure(0, 6)
    circuit.measure(1, 4)
    reference, measurements = split_circuit(circuit)
    physical, initial, final, _ = native_compile(reference, make_device("line", 4), CONFIGS[-1])
    exported = load_qasm(export_qasm(physical, measurements, final, 7))
    recovered, physical_measurements = split_circuit(exported)
    assert physical_measurements == [[final[q], c] for q, c in measurements]
    recovered.global_phase = physical.global_phase
    np.testing.assert_allclose(
        oracle_logical_matrix(recovered, initial, final),
        Operator(reference).data,
        atol=1e-12,
        rtol=0,
    )
    # A sparse classical register must retain zeros in every unmeasured bit.
    state = Operator(physical).data[:, 0]
    exported_distribution = np.zeros(128)
    for basis, amplitude in enumerate(state):
        bits = sum(((basis >> q) & 1) << c for q, c in physical_measurements)
        exported_distribution[bits] += abs(amplitude) ** 2
    expected_distribution = np.zeros(128)
    for basis, amplitude in enumerate(Operator(reference).data[:, 0]):
        bits = sum(((basis >> q) & 1) << c for q, c in measurements)
        expected_distribution[bits] += abs(amplitude) ** 2
    np.testing.assert_allclose(exported_distribution, expected_distribution, atol=1e-12, rtol=0)
    report = compile_circuit(circuit, budget=1, strategy="random", baselines=False, noisy=False)
    assert "phase" in report["export_note"].lower()
    assert "initial_mapping" in report["export_note"] and "final_mapping" in report["export_note"]


def test_global_phase_is_not_forgiven_by_verification():
    reference = QuantumCircuit(3)
    reference.ry(0.47, 0)
    reference.cx(0, 2)
    physical, initial, final, _ = native_compile(reference, make_device("line", 3), CONFIGS[-1])
    physical.global_phase += 0.01
    assert not verify(reference, physical, initial, final)["passed"]


def test_wrong_initial_permutation_is_detected_with_asymmetric_input_operator():
    reference = QuantumCircuit(3)
    reference.ry(0.47, 0)
    reference.rx(0.88, 1)
    reference.cx(0, 2)
    physical, initial, final, _ = native_compile(reference, make_device("line", 3), CONFIGS[-1])
    initial[0], initial[1] = initial[1], initial[0]
    assert not verify(reference, physical, initial, final)["passed"]


def test_verifier_rejects_measurement_instead_of_silently_ignoring_it():
    reference = QuantumCircuit(2)
    reference.h(0)
    physical = reference.copy()
    physical.measure_all()
    with pytest.raises(ValueError):
        verify(reference, physical, [0, 1], [0, 1])


def test_verifier_allows_routing_expansion_beyond_input_operation_limit():
    reference = QuantumCircuit(2)
    reference.h(0)
    physical = QuantumCircuit(2)
    for _ in range(401):
        physical.h(0)
    assert verify(reference, physical, [0, 1], [0, 1])["passed"]
