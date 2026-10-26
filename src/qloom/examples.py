"""Seeded, bounded examples and disjoint circuit-family benchmark generators."""

import numpy as np
from qiskit import QuantumCircuit, qasm2


def generate(family="random", n=5, seed=0, layers=5, measured=False):
    rng = np.random.default_rng(seed)
    qc = QuantumCircuit(n, n if measured else 0, name=f"{family}-{n}-{seed}")
    if family == "ghz":
        qc.h(0)
        for q in range(1, n):
            qc.cx(0, q)
    elif family == "qft":
        for q in range(n):
            qc.h(q)
            for t in range(q + 1, n):
                angle = np.pi / (2 ** (t - q))
                # CP decomposition in the supported gate contract.
                qc.p(angle / 2, q)
                qc.cx(q, t)
                qc.p(-angle / 2, t)
                qc.cx(q, t)
                qc.p(angle / 2, t)
    elif family == "mirror":
        qc.h(0)
        for _ in range(layers):
            a, b = rng.choice(n, 2, replace=False).tolist()
            qc.cx(a, b)
            spectator = next(q for q in range(n) if q not in (a, b)) if n > 2 else None
            if spectator is not None:
                qc.rz(float(rng.uniform(-2, 2)), spectator)
            qc.cx(a, b)
        qc.ry(0.7, n - 1)
    elif family == "qaoa":
        for q in range(n):
            qc.h(q)
        for layer in range(layers):
            for a in range(n):
                b = (a + 2) % n
                if a != b:
                    qc.cx(a, b)
                    qc.rz(0.2 + layer * 0.1, b)
                    qc.cx(a, b)
            for q in range(n):
                qc.rx(0.4 + layer * 0.07, q)
    elif family == "starphase":
        qc.h(0)
        for q in reversed(range(1, n)):
            qc.cx(0, q)
            qc.rz(float(rng.uniform(-1, 1)), 0)
            qc.cx(0, q)
        for q in range(n):
            qc.ry(float(rng.uniform(-1, 1)), q)
    elif family == "random":
        for _ in range(layers):
            for q in range(n):
                getattr(qc, rng.choice(["rx", "ry", "rz"]))(float(rng.uniform(-np.pi, np.pi)), q)
            for _ in range(n):
                a, b = rng.choice(n, 2, replace=False).tolist()
                qc.cx(a, b)
    else:
        raise ValueError(f"Unknown circuit family: {family}")
    if measured:
        for q in range(n):
            qc.measure(q, n - 1 - q)
    return qc


def example_list():
    specs = [
        ("ghz", 5, 7, 3, "GHZ fanout", "Five-qubit entanglement on a sparse processor."),
        ("qaoa", 5, 13, 2, "QAOA interaction ring", "Nonlocal phase interactions and mixer rotations."),
        ("mirror", 5, 21, 8, "Commuting mirror", "Inverse entanglers separated by spectator rotations."),
        ("qft", 5, 11, 2, "Fourier weave", "Controlled-phase decomposition with long-range interactions."),
        (
            "random",
            5,
            42,
            3,
            "Seeded random circuit",
            "A fixed, reproducible stress case with reversed classical outputs.",
        ),
    ]
    return [
        {
            "id": f,
            "name": name,
            "description": description,
            "qasm": qasm2.dumps(generate(f, n, s, l, measured=True)),
        }
        for f, n, s, l, name, description in specs
    ]
