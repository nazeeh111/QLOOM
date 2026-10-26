"""Bounded circuit contract and loss-aware OpenQASM 2 serialization."""

import math

from qiskit import QuantumCircuit, qasm2
from qiskit.circuit import Barrier, Measure
from qiskit.circuit import library as gates

STANDARD_CLASSES = {
    "id": gates.IGate,
    "h": gates.HGate,
    "x": gates.XGate,
    "y": gates.YGate,
    "z": gates.ZGate,
    "s": gates.SGate,
    "sdg": gates.SdgGate,
    "t": gates.TGate,
    "tdg": gates.TdgGate,
    "rx": gates.RXGate,
    "ry": gates.RYGate,
    "rz": gates.RZGate,
    "p": gates.PhaseGate,
    "u": gates.UGate,
    "u1": gates.U1Gate,
    "u2": gates.U2Gate,
    "u3": gates.U3Gate,
    "cx": gates.CXGate,
    "cz": gates.CZGate,
    "swap": gates.SwapGate,
    "barrier": Barrier,
    "measure": Measure,
}

SUPPORTED = {
    "id",
    "h",
    "x",
    "y",
    "z",
    "s",
    "sdg",
    "t",
    "tdg",
    "rx",
    "ry",
    "rz",
    "p",
    "u",
    "u1",
    "u2",
    "u3",
    "cx",
    "cz",
    "swap",
    "barrier",
    "measure",
}
MAX_OPERATIONS = 400


def load_qasm(text: str) -> QuantumCircuit:
    if len(text.encode()) > 100_000:
        raise ValueError("OpenQASM input exceeds 100 KB.")
    # qelib1.inc is resolved by Qiskit; arbitrary filesystem includes are forbidden.
    import re

    clean = re.sub(r"//[^\n]*", "", text)
    if re.search(r"\b(gate|opaque|if)\b", clean):
        raise ValueError("Custom gate declarations, opaque gates and conditions are unsupported.")
    for declaration, limit in (("qreg", 8), ("creg", 16)):
        sizes = re.findall(r"\b" + declaration + r"\s+[a-zA-Z_][a-zA-Z_0-9]*\s*\[\s*([0-9]+)\s*\]", clean)
        if sum(int(size) for size in sizes) > limit:
            raise ValueError(f"Input exceeds {limit} declared {declaration} bits.")
    includes = re.findall(r'\binclude\s+"([^"]+)"', re.sub(r"//[^\n]*", "", text))
    if any(path != "qelib1.inc" for path in includes):
        raise ValueError("Only the standard qelib1.inc include is supported.")
    if not re.search(r"\bOPENQASM\s+2(?:\.0)?\s*;", text):
        raise ValueError("v0.1 accepts OpenQASM 2.0 only.")
    try:
        qc = qasm2.loads(text, include_path=(), custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
    except Exception as exc:
        raise ValueError(f"Invalid or unsupported OpenQASM 2: {exc}") from exc
    validate(qc)
    return qc


def validate(qc: QuantumCircuit, max_operations: int | None = MAX_OPERATIONS):
    if not 2 <= qc.num_qubits <= 8:
        raise ValueError("v0.1 supports circuits with 2..8 qubits; no ancillas.")
    if (max_operations is not None and len(qc.data) > max_operations) or qc.num_clbits > 16:
        raise ValueError("Circuit exceeds 400 operations or 16 classical bits.")
    if qc.parameters:
        raise ValueError("Bind all circuit parameters before compilation.")
    measured = False
    seen_q, seen_c = set(), set()
    for inst in qc.data:
        name = inst.operation.name
        if (
            name not in SUPPORTED
            or inst.operation.base_class is not STANDARD_CLASSES.get(name)
            or getattr(inst.operation, "condition", None) is not None
        ):
            raise ValueError(f"Unsupported operation: {name}. No reset, control flow or conditions.")
        if any(not math.isfinite(float(p)) for p in inst.operation.params):
            raise ValueError("Gate parameters must be finite.")
        if name == "measure":
            measured = True
            q, c = qc.find_bit(inst.qubits[0]).index, qc.find_bit(inst.clbits[0]).index
            if q in seen_q or c in seen_c:
                raise ValueError("Repeated qubit measurement or classical overwrite is unsupported.")
            seen_q.add(q)
            seen_c.add(c)
        elif measured and name != "barrier":
            raise ValueError("Only terminal measurements are supported.")
    if not math.isfinite(float(qc.global_phase)):
        raise ValueError("Global phase must be finite.")


def split_circuit(qc: QuantumCircuit, max_operations: int | None = MAX_OPERATIONS):
    validate(qc, max_operations=max_operations)
    unitary = QuantumCircuit(qc.num_qubits, name=qc.name)
    unitary.global_phase = qc.global_phase
    measurements = []
    for inst in qc.data:
        q = [qc.find_bit(b).index for b in inst.qubits]
        if inst.operation.name == "measure":
            measurements.append([q[0], qc.find_bit(inst.clbits[0]).index])
        elif inst.operation.name != "barrier":
            unitary.append(inst.operation, q)
    return unitary, measurements


def operations(qc):
    return [
        {
            "gate": i.operation.name,
            "qubits": [qc.find_bit(q).index for q in i.qubits],
            "params": [float(p) for p in i.operation.params],
        }
        for i in qc.data
        if i.operation.name not in {"barrier", "measure"}
    ]


def serialize_input(qc):
    _, measurements = split_circuit(qc)
    return {
        "name": qc.name,
        "n_qubits": qc.num_qubits,
        "n_clbits": qc.num_clbits,
        "operations": operations(qc),
        "measurements": measurements,
        "global_phase": float(qc.global_phase),
        "qasm": qasm2.dumps(qc),
    }


def export_qasm(physical, measurements, final_mapping, n_clbits):
    out = physical.copy()
    if n_clbits:
        from qiskit import ClassicalRegister

        out.add_register(ClassicalRegister(n_clbits, "c"))
    for logical, classical in measurements:
        out.measure(final_mapping[logical], classical)
    return qasm2.dumps(out)
