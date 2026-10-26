"""QLOOM's native compiler, independent of Qiskit's layout/routing/transpile.

Three routing policies use shortest-path-progress swaps. The lookahead router
scores the next interaction window. Every swap updates logical token locations.
"""

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import UGate

from .circuits import STANDARD_CLASSES, operations


@dataclass(frozen=True)
class Config:
    layout: str = "interaction"
    routing: str = "lookahead"
    lookahead: int = 6
    rewrite: bool = True

    def to_dict(self):
        return asdict(self)


CONFIGS = [
    Config(layout, routing, 6, rewrite)
    for layout, routing, rewrite in product(
        ("identity", "central", "interaction", "reverse"), ("control", "target", "lookahead"), (False, True)
    )
]


def commute(a, b):
    aq, bq = set(a["qubits"]), set(b["qubits"])
    if not aq & bq:
        return True
    if a["gate"] == b["gate"] == "cx":
        ac, at = a["qubits"]
        bc, bt = b["qubits"]
        return ac != bt and at != bc
    # Z rotations commute on CX control; X rotations on CX target.
    if b["gate"] == "cx" and len(a["qubits"]) == 1:
        q = a["qubits"][0]
        return (a["gate"] in {"z", "s", "sdg", "t", "tdg", "rz", "p"} and q == b["qubits"][0]) or (
            a["gate"] in {"x", "rx"} and q == b["qubits"][1]
        )
    if a["gate"] == "cx" and len(b["qubits"]) == 1:
        return commute(b, a)
    return False


def rewrite_ops(ops):
    """Cancel commuting inverse pairs and fold equal-axis rotations exactly.

    Traversal stops at the first noncommuting gate; angles are NOT reduced modulo
    2π because that would discard a meaningful global phase.
    """
    out, edits = [], 0
    inverse = {
        "h": "h",
        "x": "x",
        "y": "y",
        "z": "z",
        "cx": "cx",
        "cz": "cz",
        "swap": "swap",
        "s": "sdg",
        "sdg": "s",
        "t": "tdg",
        "tdg": "t",
    }
    for original in ops:
        a = {**original, "qubits": list(original["qubits"]), "params": list(original["params"])}
        consumed = False
        for j in range(len(out) - 1, -1, -1):
            b = out[j]
            same = a["qubits"] == b["qubits"]
            if same and inverse.get(a["gate"]) == b["gate"]:
                del out[j]
                edits += 1
                consumed = True
                break
            if same and a["gate"] == b["gate"] and a["gate"] in {"rx", "ry", "rz", "p"}:
                b["params"][0] += a["params"][0]
                if abs(b["params"][0]) < 1e-14:
                    del out[j]
                edits += 1
                consumed = True
                break
            if not commute(a, b):
                break
        if not consumed:
            out.append(a)
    return out, edits


def ops_circuit(ops, n, phase=0.0):
    qc = QuantumCircuit(n)
    qc.global_phase = phase
    for op in ops:
        qc.append(STANDARD_CLASSES[op["gate"]](*op["params"]), op["qubits"])
    return qc


def interaction_matrix(ops, n, reverse=False):
    weights = np.zeros((n, n))
    sequence = list(reversed(ops)) if reverse else ops
    pairs = [o["qubits"] for o in sequence if len(o["qubits"]) == 2]
    for i, (a, b) in enumerate(pairs):
        w = 1 + 3 / (1 + i / 4)
        weights[a, b] += w
        weights[b, a] += w
    return weights


def initial_layout(ops, device, kind):
    n = device.n_qubits
    if kind == "identity":
        return list(range(n))
    d = np.asarray(device.distances())
    w = interaction_matrix(ops, n, kind == "reverse")
    logical_order = sorted(range(n), key=lambda x: (-w[x].sum(), x))
    physical_order = sorted(range(n), key=lambda x: (d[x].sum(), x))
    mapping = [0] * n
    for q, p in zip(logical_order, physical_order):
        mapping[q] = p
    if kind == "central":
        return mapping

    # Greedy placement refinement minimizes weighted interaction distance.
    # Strict improvements + deterministic tie order make the result reproducible.
    def cost(m):
        return float(np.sum(w * d[np.ix_(m, m)]))

    current = cost(mapping)
    for _ in range(n * n):
        best = None
        for a in range(n):
            for b in range(a + 1, n):
                trial = mapping.copy()
                trial[a], trial[b] = trial[b], trial[a]
                value = cost(trial)
                if value < current - 1e-10 and (best is None or value < best[0] - 1e-10):
                    best = value, trial
        if best is None:
            break
        current, mapping = best
    return mapping


def native_compile(reference, device, config):
    if reference.num_qubits != device.n_qubits:
        raise ValueError("Device width must equal logical width in v0.1; ancillas are excluded.")
    raw = operations(reference)
    ops, edits = rewrite_ops(raw) if config.rewrite else (raw, 0)
    prepared = ops_circuit(ops, device.n_qubits, float(reference.global_phase))
    # Translation only, with no layout, routing or whole-circuit optimization.
    from qiskit.circuit.equivalence_library import SessionEquivalenceLibrary
    from qiskit.transpiler import PassManager
    from qiskit.transpiler.passes import BasisTranslator

    normalized = PassManager(BasisTranslator(SessionEquivalenceLibrary, ["u", "cx"])).run(prepared)
    ops = operations(normalized)
    mapping = initial_layout(ops, device, config.layout)
    initial = mapping.copy()
    physical = QuantumCircuit(device.n_qubits)
    physical.global_phase = normalized.global_phase
    history = [
        {
            "step": 0,
            "kind": "layout",
            "label": f"{config.layout} initial placement",
            "qubits": [],
            "mapping": mapping.copy(),
        }
    ]
    if edits:
        history.append(
            {
                "step": 0,
                "kind": "rewrite",
                "label": f"{edits} commuting inverse/fold rewrites",
                "qubits": [],
                "mapping": mapping.copy(),
            }
        )
    d = device.distances()
    edges = sorted({tuple(sorted(e)) for e in device.edges})
    swap_count = 0
    for index, op in enumerate(ops):
        if op["gate"] == "cx":
            c, t = op["qubits"]
            while not device.adjacent(mapping[c], mapping[t]):
                distance = d[mapping[c]][mapping[t]]
                choices = []
                for a, b in edges:
                    if not {a, b} & {mapping[c], mapping[t]}:
                        continue
                    trial = [b if p == a else a if p == b else p for p in mapping]
                    if d[trial[c]][trial[t]] >= distance:
                        continue
                    future = [x for x in ops[index + 1 :] if x["gate"] == "cx"][: config.lookahead]
                    score = sum(
                        d[trial[x["qubits"][0]]][trial[x["qubits"][1]]] / (k + 1)
                        for k, x in enumerate(future)
                    )
                    if config.routing == "control":
                        score = 0 if mapping[c] in (a, b) else 100
                    elif config.routing == "target":
                        score = 0 if mapping[t] in (a, b) else 100
                    choices.append((score, a, b, trial))
                if not choices:
                    raise RuntimeError("No distance-reducing swap on connected device.")
                _, a, b, mapping = min(choices, key=lambda x: (x[0], x[1], x[2]))
                physical.cx(a, b)
                physical.cx(b, a)
                physical.cx(a, b)
                swap_count += 1
                history.append(
                    {
                        "step": len(physical.data),
                        "kind": "swap",
                        "label": f"Route logical CX {c}→{t}: SWAP {a}↔{b}",
                        "qubits": [a, b],
                        "mapping": mapping.copy(),
                    }
                )
            physical.cx(mapping[c], mapping[t])
        elif op["gate"] == "u":
            physical.append(UGate(*op["params"]), [mapping[op["qubits"][0]]])
        else:
            raise RuntimeError(f"Translation produced unsupported native gate {op['gate']}")
    if config.rewrite:
        # A second native cancellation sweep can remove routing-induced CX pairs.
        reduced, post_edits = rewrite_ops(operations(physical))
        physical = ops_circuit(reduced, device.n_qubits, float(physical.global_phase))
        if post_edits:
            history.append(
                {
                    "step": len(physical.data),
                    "kind": "rewrite",
                    "label": f"{post_edits} post-route cancellations; routing replay records pre-sweep events",
                    "qubits": [],
                    "mapping": mapping.copy(),
                }
            )
    history.append(
        {
            "step": len(physical.data),
            "kind": "complete",
            "label": f"Native routing complete: {swap_count} swaps",
            "qubits": [],
            "mapping": mapping.copy(),
        }
    )
    return physical, initial, mapping, history
