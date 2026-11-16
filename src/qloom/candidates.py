"""One acceptance boundary for generated and recovered compiler candidates."""

from .circuits import export_qasm, load_qasm, operations, split_circuit
from .cost import metrics
from .verify import verify, verify_measurement_export


def candidate_record(
    reference,
    physical,
    initial,
    final,
    device,
    measurements,
    n_clbits,
    identifier,
    config,
    elapsed,
    history=None,
    seed=0,
    tolerance=1e-8,
):
    verification = verify(reference, physical, initial, final, seed, tolerance)
    if not verification["passed"]:
        raise ValueError(
            f"Candidate {identifier} failed independent equivalence: {verification['max_error']:.3g}"
        )
    qasm = export_qasm(physical, measurements, final, n_clbits)
    if measurements:
        exported = load_qasm(qasm, max_operations=None)
        _, actual = split_circuit(exported, max_operations=None)
        if actual != [[final[q], c] for q, c in measurements]:
            raise ValueError("Export changed classical measurement destinations.")
        measurement_check = verify_measurement_export(reference, exported, initial, measurements, seed)
        if not measurement_check["measurement_passed"]:
            raise ValueError("Export failed independent measured-output simulation.")
        verification.update(measurement_check)
    m = metrics(physical, device, elapsed)
    return {
        "id": identifier,
        "config": config,
        "metrics": m,
        "verification": verification,
        "initial_mapping": list(initial),
        "final_mapping": list(final),
        "operations": operations(physical),
        "history": history or [],
        "qasm": qasm,
        "global_phase": float(physical.global_phase),
        "model_prediction": None,
        "elapsed_s": elapsed,
    }


def revalidate_candidate(record, reference, device, measurements, n_clbits, seed, tolerance=1e-8):
    """Recover QASM+phase+layout and check both redundant representations."""
    if not isinstance(record["qasm"], str) or type(record["global_phase"]) not in (int, float):
        raise ValueError("Cached QASM and phase have invalid types.")
    if record["verification"]["passed"] is not True:
        raise ValueError("Cached candidate was not verified.")
    if measurements and record["verification"].get("measurement_passed") is not True:
        raise ValueError("Cached measurement verification is missing or failed.")
    exported = load_qasm(record["qasm"], max_operations=None)
    physical, actual = split_circuit(exported, max_operations=None)
    if exported.num_clbits != n_clbits or operations(physical) != record["operations"]:
        raise ValueError("Cached QASM disagrees with operations or classical width.")
    physical.global_phase = record["global_phase"]
    initial, final = record["initial_mapping"], record["final_mapping"]
    for mapping in (initial, final):
        if (
            not isinstance(mapping, list)
            or any(type(q) is not int for q in mapping)
            or sorted(mapping) != list(range(reference.num_qubits))
        ):
            raise ValueError("Cached mappings must be qubit bijections.")
    if actual != [[final[q], c] for q, c in measurements]:
        raise ValueError("Cached QASM changed classical measurement destinations.")
    checked = candidate_record(
        reference, physical, initial, final, device, measurements, n_clbits,
        record["id"], record["config"], record["metrics"]["compile_time_s"],
        record["history"], seed, tolerance,
    )
    if record["metrics"] != checked["metrics"]:
        raise ValueError("Cached metrics disagree with the recovered circuit.")
    # Recheck the stored export itself, not just the newly generated one.
    if measurements:
        check = verify_measurement_export(reference, exported, initial, measurements, seed)
        if not check["measurement_passed"]:
            raise ValueError("Cached export failed measured-output simulation.")
        checked["verification"].update(check)
    record["verification"] = checked["verification"]
