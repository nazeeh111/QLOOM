"""Internal JSON-over-stdio process boundary for optional compiler baselines.

Use :func:`qloom.baselines.compile_baseline` rather than invoking this module.
The parent owns timeout, process-group cleanup, and independent verification.
"""

from __future__ import annotations

import json
import math
import os
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace

from qiskit import qasm2

from .baselines import _compile_baseline_direct


def main() -> int:
    """Read one internal request and emit exactly one JSON response."""
    saved_stdout = os.dup(1)
    try:
        request = json.load(sys.stdin)
        if request.get("name") not in {"qmap", "bqskit"}:
            raise ValueError("Worker supports only qmap and bqskit.")
        phase = float(request["global_phase"])
        if not math.isfinite(phase):
            raise ValueError("Global phase must be finite.")
        device_data = request["device"]
        device = SimpleNamespace(
            n_qubits=int(device_data["n_qubits"]),
            edges=[tuple(map(int, edge)) for edge in device_data["edges"]],
        )
        # Route Python and native-library output to stderr. The transport's
        # stdout is reserved for JSON, even if a dependency prints diagnostics.
        sys.stdout.flush()
        os.dup2(2, 1)
        with redirect_stdout(sys.stderr):
            qc = qasm2.loads(request["qasm"], custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
            qc.global_phase = phase
            out, initial, final, metadata = _compile_baseline_direct(
                qc,
                device,
                request["name"],
                int(request["seed"]),
            )
            response = {
                "qasm": qasm2.dumps(out),
                "global_phase": float(out.global_phase),
                "initial": initial,
                "final": final,
                "metadata": metadata,
            }
    except Exception as exc:
        response = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        sys.stdout.flush()
        os.dup2(saved_stdout, 1)
        os.close(saved_stdout)
    print(json.dumps(response, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
