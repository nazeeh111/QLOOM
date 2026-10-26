"""Hardware-constrained metrics with transparent synthetic assumptions."""

import math

from .circuits import operations


def metrics(qc, device, compile_time_s=0.0):
    available = [0.0] * device.n_qubits
    two, single = 0, 0
    for op in operations(qc):
        qs = op["qubits"]
        if op["gate"] not in device.basis_gates:
            raise ValueError(f"Gate {op['gate']} is outside device basis.")
        if len(qs) == 2:
            if not device.adjacent(*qs):
                raise ValueError("Candidate violates processor connectivity.")
            two += 1
            duration = device.two_duration_ns
        else:
            single += 1
            duration = device.single_duration_ns
        end = max(available[q] for q in qs) + duration
        for q in qs:
            available[q] = end
    success = (1 - device.two_error) ** two * (1 - device.single_error) ** single
    # Product of independent no-error probabilities; not observed fidelity.
    objective = two + 0.04 * qc.depth() + 8 * (-math.log(max(success, 1e-300)))
    return {
        "two_qubit_gates": two,
        "single_qubit_gates": single,
        "depth": qc.depth(),
        "duration_ns": max(available),
        "estimated_success": success,
        "objective": objective,
        "compile_time_s": compile_time_s,
    }


def pareto(candidates):
    def vector(c):
        m = c["metrics"]
        return (m["two_qubit_gates"], m["duration_ns"], 1 - m["estimated_success"])

    return [
        c["id"]
        for c in candidates
        if not any(
            all(x <= y for x, y in zip(vector(other), vector(c)))
            and any(x < y for x, y in zip(vector(other), vector(c)))
            for other in candidates
        )
    ]
