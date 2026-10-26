"""Public report interfaces. All mappings are logical-index -> physical-index."""

from typing import NotRequired, TypedDict


class Operation(TypedDict):
    gate: str
    qubits: list[int]
    params: list[float]


class Verification(TypedDict):
    passed: bool
    method: str
    max_error: float
    global_phase_error: float
    randomized_max_error: float
    trials: int
    tolerance: float


class Metrics(TypedDict):
    two_qubit_gates: int
    single_qubit_gates: int
    depth: int
    duration_ns: float
    estimated_success: float
    objective: float
    compile_time_s: float


class Candidate(TypedDict):
    id: str
    config: dict
    metrics: Metrics
    verification: Verification
    initial_mapping: list[int]
    final_mapping: list[int]
    operations: list[Operation]
    qasm: str
    global_phase: float
    history: list[dict]
    model_prediction: float | None
    elapsed_s: float
    status: NotRequired[str]
    name: NotRequired[str]


class CompilationReport(TypedDict):
    schema_version: str
    seed: int
    strategy: str
    budget: int
    device: dict
    input: dict
    candidates: list[Candidate]
    best_id: str
    pareto_ids: list[str]
    baselines: list[dict]
    noise: dict
    model: dict
    search_time_s: float
    optimizer_time_s: float
    elapsed_s: float
    cache_hit: bool
    export_note: str
