"""Shared report contracts for generation and cached-report admission."""

EXPORT_NOTE = "QASM2 omits global phase and layout semantics. Export JSON alongside QASM. Initialize inputs using initial_mapping; interpret unitary outputs using final_mapping. Exported measurement statements already map logical results to original classical bit indices. All model noise is simulated; no real QPU execution."
NOISE_NOT_RUN = "Enable noisy=True and install the research extras."
NOISE_LIMIT = "Density-matrix demo limited to <=6 qubits; logical proof still runs."
NOISE_UNAVAILABLE = "Install qloom-compiler[research] for noisy density-matrix simulation."
NOISE_METHOD = "Aer exact density matrix; zero logical input; output distribution fidelity"
NOISE_ASSUMPTIONS = "Synthetic U/CX depolarizing errors + independent symmetric readout. No T1/T2, crosstalk, pulse physics or QPU data. Input comparison is Qiskit level 0 on the SAME device. Distribution similarity is not equivalence proof."


def baseline_names(baselines, noisy):
    if baselines:
        return ["qiskit-0", "qiskit-1", "qiskit-2", "qiskit-3", "qmap", "bqskit"]
    return ["qiskit-0"] if noisy else []


def baseline_tolerance(name):
    return 1e-7 if name == "bqskit" else 1e-8
