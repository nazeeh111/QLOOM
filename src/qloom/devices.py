"""Explicit synthetic, bidirectional U/CX processors; no real QPU claims."""

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Device:
    name: str
    n_qubits: int
    edges: tuple[tuple[int, int], ...]
    single_error: float = 0.0005
    two_error: float = 0.012
    readout_error: float = 0.018
    single_duration_ns: float = 35
    two_duration_ns: float = 300
    noise_source: str = "synthetic depolarizing + symmetric readout; no QPU calibration"
    basis_gates: tuple[str, ...] = ("u", "cx")

    def __post_init__(self):
        if not 2 <= self.n_qubits <= 8:
            raise ValueError("Devices support 2..8 physical qubits in v0.1.")
        for u, v in self.edges:
            if u == v or min(u, v) < 0 or max(u, v) >= self.n_qubits:
                raise ValueError("Invalid device coupling edge.")
        if not self.edges or any(
            not math.isfinite(x) or not 0 <= x < 1
            for x in (self.single_error, self.two_error, self.readout_error)
        ):
            raise ValueError("Noise probabilities must be finite and in [0,1).")
        if any(not math.isfinite(x) or x <= 0 for x in (self.single_duration_ns, self.two_duration_ns)):
            raise ValueError("Gate durations must be finite and positive.")
        if set(self.basis_gates) != {"u", "cx"}:
            raise ValueError("v0.1 supports the explicit U/CX native gate set only.")
        if any(math.isinf(x) for row in self.distances() for x in row):
            raise ValueError("Device must be connected.")

    def distances(self):
        n = self.n_qubits
        d = [[0 if a == b else (1 if self.adjacent(a, b) else math.inf) for b in range(n)] for a in range(n)]
        for k in range(n):
            for i in range(n):
                for j in range(n):
                    d[i][j] = min(d[i][j], d[i][k] + d[k][j])
        return d

    def adjacent(self, a, b):
        return (a, b) in self.edges or (b, a) in self.edges

    def to_dict(self):
        return asdict(self)


def make_device(topology: str = "line", n: int = 5, **noise) -> Device:
    if topology == "line":
        edges = [(i, i + 1) for i in range(n - 1)]
    elif topology == "ring":
        edges = list(dict.fromkeys(tuple(sorted((i, (i + 1) % n))) for i in range(n)))
    elif topology == "star":
        edges = [(0, i) for i in range(1, n)]
    elif topology == "grid":
        width = math.ceil(math.sqrt(n))
        edges = [
            (i, j)
            for i in range(n)
            for j in range(i + 1, n)
            if (j == i + width or (j == i + 1 and i // width == j // width))
        ]
    else:
        raise ValueError("Unknown topology; choose line, ring, star, grid.")
    return Device(f"{topology}-{n}", n, tuple(edges), **noise)


def device_named(name: str) -> Device:
    try:
        shape, n = name.rsplit("-", 1)
        return make_device(shape, int(n))
    except (ValueError, TypeError) as exc:
        raise ValueError("Device must be topology-N, e.g. line-5 (2..8 qubits).") from exc
