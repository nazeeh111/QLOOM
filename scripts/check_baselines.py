"""A small real optional-dependency check; timeouts are visible test failures."""

from qiskit import QuantumCircuit

from qloom.compiler import compile_circuit
from qloom.devices import make_device

if __name__ == "__main__":
    qc = QuantumCircuit(3, 3)
    qc.h(0)
    qc.cx(0, 2)
    qc.ry(0.2, 1)
    qc.global_phase = 0.43
    qc.measure([0, 1, 2], [2, 1, 0])
    r = compile_circuit(qc, make_device("line", 3), budget=2)
    for b in r["baselines"]:
        print(b["name"], b["status"], b.get("reason", ""))
        assert b["status"] == "ok", b
        assert b["verification"]["passed"]
    assert r["noise"]["method"].startswith("Aer exact")
    assert 0 <= r["noise"]["optimized_fidelity"] <= 1
