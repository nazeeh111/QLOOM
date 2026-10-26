"""Graph-aware summaries, with no external graph model or pretrained service."""

import numpy as np

from .circuits import operations
from .routing import initial_layout, interaction_matrix, rewrite_ops

FEATURE_NAMES = [
    "qubits",
    "operations",
    "two_qubit_count",
    "single_qubit_count",
    "interaction_density",
    "interaction_max_degree",
    "interaction_mean_degree",
    "interaction_degree_std",
    "hardware_density",
    "hardware_diameter",
    "hardware_mean_distance",
    "hardware_degree_std",
    "laplacian_gap",
    "placement_mean_distance",
    "placement_max_distance",
    "early_distance",
    "late_distance",
    "commutation_reductions",
    "single_error",
    "two_error",
    "layout_identity",
    "layout_central",
    "layout_interaction",
    "layout_reverse",
    "route_control",
    "route_target",
    "route_lookahead",
    "rewrite_enabled",
]


def features(qc, device, config, graph_aware=True):
    n = qc.num_qubits
    ops = operations(qc)
    pairs = [o["qubits"] for o in ops if len(o["qubits"]) == 2]
    w = interaction_matrix(ops, n)
    adjacency = (w > 0).astype(float)
    degree = adjacency.sum(axis=1)
    hd = np.asarray(device.distances())
    ha = (hd == 1).astype(float)
    lap = np.diag(ha.sum(axis=1)) - ha
    eig = np.linalg.eigvalsh(lap)
    m = initial_layout(ops, device, config.layout)
    distances = [hd[m[a], m[b]] for a, b in pairs] or [0.0]
    graph = [
        float(adjacency.sum() / (n * (n - 1))),
        float(degree.max()),
        float(degree.mean()),
        float(degree.std()),
        float(ha.sum() / (n * (n - 1))),
        float(hd.max()),
        float(hd.mean()),
        float(ha.sum(axis=1).std()),
        float(eig[1]),
        float(np.mean(distances)),
        float(max(distances)),
        float(np.mean(distances[:6])),
        float(np.mean(distances[-6:])),
    ]
    _, edits = rewrite_ops(ops)
    vals = [
        n,
        len(ops),
        len(pairs),
        len(ops) - len(pairs),
        *(graph if graph_aware else [0.0] * len(graph)),
        edits,
        device.single_error,
        device.two_error,
        *[float(config.layout == x) for x in ("identity", "central", "interaction", "reverse")],
        *[float(config.routing == x) for x in ("control", "target", "lookahead")],
        float(config.rewrite),
    ]
    return vals
