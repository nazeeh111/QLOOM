"""Exact density-matrix noise simulation, separate from semantics proof."""

import numpy as np

from .circuits import operations
from .report_policy import NOISE_ASSUMPTIONS, NOISE_LIMIT, NOISE_METHOD, NOISE_UNAVAILABLE
from .verify import classical_probabilities, evolve, permutation


def distribution_fidelity(p, q):
    return float(np.clip(np.sum(np.sqrt(np.maximum(p, 0) * np.maximum(q, 0))) ** 2, 0, 1))


def simulate_probabilities(qc, final, device, measurements, n_clbits, seed=0):
    try:
        from qiskit_aer import AerSimulator
        from qiskit_aer.noise import NoiseModel, depolarizing_error
    except ImportError as exc:
        raise ImportError(NOISE_UNAVAILABLE) from exc
    noise = NoiseModel()
    noise.add_all_qubit_quantum_error(depolarizing_error(device.single_error, 1), ["u"])
    noise.add_all_qubit_quantum_error(depolarizing_error(device.two_error, 2), ["cx"])
    circuit = qc.copy()
    circuit.save_probabilities()
    simulator = AerSimulator(method="density_matrix", noise_model=noise, max_parallel_threads=1)
    physical = np.asarray(simulator.run(circuit, seed_simulator=seed).result().data(0)["probabilities"])
    logical = physical[permutation(final)]
    # Apply symmetric independent readout flips to measured logical bits only.
    readout = logical.copy()
    targets = [q for q, _ in measurements] if measurements else list(range(device.n_qubits))
    ids = np.arange(len(readout))
    for q in targets:
        readout = (1 - device.readout_error) * readout + device.readout_error * readout[ids ^ (1 << q)]
    return classical_probabilities(readout, measurements, n_clbits)


def compare_noise(reference, best, baseline, device, measurements, n_clbits, seed=0):
    if reference.num_qubits > 6:
        return {
            "method": "not-run",
            "assumptions": NOISE_LIMIT,
        }
    zero = np.zeros(1 << reference.num_qubits, complex)
    zero[0] = 1
    ideal = (
        np.abs(evolve(operations(reference), reference.num_qubits, zero, float(reference.global_phase))) ** 2
    )
    ideal = classical_probabilities(ideal, measurements, n_clbits)
    p = simulate_probabilities(best[0], best[1], device, measurements, n_clbits, seed)
    q = simulate_probabilities(baseline[0], baseline[1], device, measurements, n_clbits, seed)
    return {
        "method": NOISE_METHOD,
        "assumptions": NOISE_ASSUMPTIONS,
        "ideal_probabilities": ideal.tolist(),
        "optimized_probabilities": p.tolist(),
        "input_probabilities": q.tolist(),
        "optimized_fidelity": distribution_fidelity(ideal, p),
        "input_fidelity": distribution_fidelity(ideal, q),
    }
