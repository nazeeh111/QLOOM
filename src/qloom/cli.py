"""QLOOM's local command line, with explicit, reproducible output bundles."""

import argparse
import json
from pathlib import Path

from .compiler import compile_circuit
from .devices import device_named
from .examples import example_list


def save_bundle(report, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    best = next(c for c in report["candidates"] if c["id"] == report["best_id"])
    (destination / "optimized.qasm").write_text(best["qasm"] + "\n")
    metadata = {
        key: best[key]
        for key in ("id", "initial_mapping", "final_mapping", "global_phase", "verification", "config")
    }
    metadata.update(
        n_qubits=report["input"]["n_qubits"],
        n_clbits=report["input"]["n_clbits"],
        measurements=report["input"]["measurements"],
        export_note=report["export_note"],
    )
    (destination / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return destination


def main(argv=None):
    p = argparse.ArgumentParser(prog="qloom", description="Verified, learned quantum compilation on your CPU")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile", help="Import OpenQASM2, search, verify and export a bundle")
    c.add_argument("input", type=Path)
    c.add_argument("--device", default="line-5")
    c.add_argument("--budget", type=int, default=4)
    c.add_argument("--seed", type=int, default=7)
    c.add_argument("--strategy", choices=["learned", "random", "heuristic"], default="learned")
    c.add_argument("--out", type=Path, default=Path("qloom-output"))
    c.add_argument("--model", type=Path)
    c.add_argument("--skip-baselines", action="store_true")
    c.add_argument("--skip-noise", action="store_true")
    c.add_argument("--cache", type=Path, help="Optional trusted local content-addressed report cache")
    s = sub.add_parser("studio", help="Run the local interactive Quantum Compiler Studio")
    s.add_argument("--port", type=int, default=8765)
    e = sub.add_parser("examples", help="Write reproducible OpenQASM examples")
    e.add_argument("--out", type=Path, default=Path("examples"))
    t = sub.add_parser("train", help="Reproduce CPU surrogate training (research extras)")
    t.add_argument("--out", type=Path, default=Path("models/surrogate.json"))
    t.add_argument("--quick", action="store_true")
    b = sub.add_parser("benchmark", help="Run the reproducible benchmark suite (research extras)")
    b.add_argument("--out", type=Path, default=Path("benchmarks/reproduced"))
    b.add_argument("--quick", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.command == "studio":
            import uvicorn

            uvicorn.run("qloom.server:app", host="127.0.0.1", port=args.port, access_log=False)
        elif args.command == "examples":
            args.out.mkdir(parents=True, exist_ok=True)
            for item in example_list():
                (args.out / f"{item['id']}.qasm").write_text(item["qasm"] + "\n")
            print(f"Wrote {len(example_list())} circuits to {args.out}")
        elif args.command == "compile":
            report = compile_circuit(
                args.input.read_text(),
                device_named(args.device),
                args.budget,
                args.seed,
                args.strategy,
                args.model,
                not args.skip_baselines,
                not args.skip_noise,
                args.cache,
            )
            save_bundle(report, args.out)
            best = next(c for c in report["candidates"] if c["id"] == report["best_id"])
            print(
                f"Verified {len(report['candidates'])} candidates. Best {best['id']}: "
                f"{best['metrics']['two_qubit_gates']} CX, depth {best['metrics']['depth']}."
            )
            print(f"Saved QASM, phase/mapping metadata and full report to {args.out}")
        elif args.command == "train":
            from .training import train_model

            summary = train_model(args.out, quick=args.quick)
            print(json.dumps(summary, indent=2))
        elif args.command == "benchmark":
            from .experiments import run_experiments

            summary = run_experiments(args.out, quick=args.quick)
            print(json.dumps(summary, indent=2))
    except (ValueError, OSError, ImportError) as exc:
        p.exit(2, f"qloom: {exc}\n")


if __name__ == "__main__":
    main()
