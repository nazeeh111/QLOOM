"""Independent NumPy interpreter. Never uses compiler rewrites or Qiskit Operator.

Basis convention: little endian, bit q is qubit q; mappings are logical->physical.
The full matrix compares complex amplitudes INCLUDING global phase.
"""

import numpy as np

from .circuits import operations, validate


def gate_matrix(name, p):
    i = 1j
    if name in {"u", "u3"}:
        t, ph, la = p
        return np.array(
            [
                [np.cos(t / 2), -np.exp(i * la) * np.sin(t / 2)],
                [np.exp(i * ph) * np.sin(t / 2), np.exp(i * (ph + la)) * np.cos(t / 2)],
            ]
        )
    if name == "u2":
        return gate_matrix("u", [np.pi / 2, *p])
    if name == "u1":
        return np.diag([1, np.exp(i * p[0])])
    mats = {
        "id": np.eye(2),
        "x": np.array([[0, 1], [1, 0]]),
        "y": np.array([[0, -i], [i, 0]]),
        "z": np.diag([1, -1]),
        "h": np.array([[1, 1], [1, -1]]) / np.sqrt(2),
        "s": np.diag([1, i]),
        "sdg": np.diag([1, -i]),
        "t": np.diag([1, np.exp(i * np.pi / 4)]),
        "tdg": np.diag([1, np.exp(-i * np.pi / 4)]),
    }
    if name in mats:
        return mats[name]
    if name in {"rx", "ry", "rz"}:
        return np.cos(p[0] / 2) * np.eye(2) - i * np.sin(p[0] / 2) * mats[name[1:]]
    if name == "p":
        return np.diag([1, np.exp(i * p[0])])
    raise ValueError(f"Independent interpreter does not support {name}")


def evolve(ops, n, state, phase=0.0):
    """Evolve a vector or columns of vectors without constructing gate unitaries."""
    a = np.array(state, dtype=complex, copy=True)
    ids = np.arange(1 << n)
    for op in ops:
        name, qs, ps = op["gate"], op["qubits"], op["params"]
        if name == "cx":
            c, t = qs
            perm = ids ^ (((ids >> c) & 1) << t)
            a = a[perm]
        elif name == "cz":
            mask = (((ids >> qs[0]) & 1) & ((ids >> qs[1]) & 1)).astype(bool)
            a[mask] *= -1
        elif name == "swap":
            c, t = qs
            diff = ((ids >> c) ^ (ids >> t)) & 1
            a = a[ids ^ (diff << c) ^ (diff << t)]
        else:
            m = gate_matrix(name, ps)
            lo = ids[(ids & (1 << qs[0])) == 0]
            hi = lo | (1 << qs[0])
            x, y = a[lo].copy(), a[hi].copy()
            a[lo], a[hi] = m[0, 0] * x + m[0, 1] * y, m[1, 0] * x + m[1, 1] * y
    return a * np.exp(1j * phase)


def permutation(mapping):
    return np.array(
        [sum(((x >> q) & 1) << p for q, p in enumerate(mapping)) for x in range(1 << len(mapping))]
    )


def logical_matrix(qc, initial, final):
    validate(qc, max_operations=None)
    if any(inst.operation.name == "measure" for inst in qc.data):
        raise ValueError(
            "Unitary verifier expects the unmeasured prefix; verify output measurement destinations separately."
        )
    n = qc.num_qubits
    if sorted(initial) != list(range(n)) or sorted(final) != list(range(n)):
        raise ValueError("Mappings must be bijections of the device qubits.")
    pin, pout = permutation(initial), permutation(final)
    # Each column starts in the encoded logical basis input.
    inputs = np.eye(1 << n, dtype=complex)[:, pin]
    return evolve(operations(qc), n, inputs, float(qc.global_phase))[pout, :]


def verify(reference, physical, initial, final, seed=0, tolerance=1e-8):
    n = reference.num_qubits
    if physical.num_qubits != n:
        raise ValueError("Ancilla verification is not supported in v0.1.")
    u = logical_matrix(reference, list(range(n)), list(range(n)))
    v = logical_matrix(physical, initial, final)
    error = float(np.max(np.abs(u - v)))
    phase = float(np.angle(np.vdot(u, v)))
    rng = np.random.default_rng(seed)
    states = rng.normal(size=(1 << n, 8)) + 1j * rng.normal(size=(1 << n, 8))
    states /= np.linalg.norm(states, axis=0)
    random_error = float(np.max(np.abs(u @ states - v @ states)))
    return {
        "passed": error <= tolerance and random_error <= tolerance,
        "method": "independent-numpy-full-unitary-including-global-phase+random-inputs",
        "max_error": error,
        "global_phase_error": abs(phase),
        "randomized_max_error": random_error,
        "trials": 8,
        "tolerance": tolerance,
    }


def classical_probabilities(probabilities, measurements, n_clbits):
    if not measurements:
        return probabilities
    out = np.zeros(1 << n_clbits)
    for x, p in enumerate(probabilities):
        c = sum(((x >> q) & 1) << b for q, b in measurements)
        out[c] += p
    return out


def verify_measurement_export(reference, exported, initial, measurements, seed=0, trials=3):
    """Check the serialized terminal measurement instrument on random inputs.

    Exact prefix equivalence is checked separately. Here a second parsing path
    inspects the actual exported destinations and simulates its classical output.
    This checks sparse/reordered outputs without using noisy-output similarity.
    """
    from .circuits import split_circuit

    physical, actual_measurements = split_circuit(exported, max_operations=None)
    n = reference.num_qubits
    rng = np.random.default_rng(seed)
    error = 0.0
    for _ in range(trials):
        state = rng.normal(size=1 << n) + 1j * rng.normal(size=1 << n)
        state /= np.linalg.norm(state)
        encoded = np.empty_like(state)
        encoded[permutation(initial)] = state
        logical_output = evolve(operations(reference), n, state, float(reference.global_phase))
        physical_output = evolve(operations(physical), n, encoded, float(physical.global_phase))
        expected = classical_probabilities(np.abs(logical_output) ** 2, measurements, exported.num_clbits)
        actual = classical_probabilities(
            np.abs(physical_output) ** 2, actual_measurements, exported.num_clbits
        )
        error = max(error, float(np.max(np.abs(expected - actual))))
    return {
        "measurement_passed": error <= 1e-8,
        "measurement_max_error": error,
        "measurement_trials": trials,
        "measurement_method": "independent NumPy statevector simulation of reparsed exported classical outputs",
    }
