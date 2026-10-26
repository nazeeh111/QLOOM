#!/usr/bin/env python3
"""Render publication figures directly from QLOOM's saved numerical records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

INK = "#142738"
BLUE = "#315cc9"
AMBER = "#cc873d"
PAPER = "#faf8f2"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Fresh render directory for visual review")
    args = parser.parse_args()
    root = args.root
    figures = args.output or root / "docs" / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelcolor": INK,
            "text.color": INK,
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "savefig.facecolor": PAPER,
            "svg.fonttype": "none",
        }
    )
    summary = json.loads((root / "benchmarks" / "summary.json").read_text())
    methods = [m for m in summary["methods"] if m["instances"]]
    order = [
        "learned",
        "random",
        "heuristic",
        "no-graph",
        "no-rewrite",
        "oracle-24",
        "qiskit-0",
        "qiskit-1",
        "qiskit-2",
        "qiskit-3",
        "qmap",
        "bqskit",
    ]
    methods.sort(key=lambda m: order.index(m["name"]) if m["name"] in order else 99)
    native = [m for m in methods if m["name"] in {"learned", "random", "heuristic", "no-graph", "oracle-24"}]
    fig, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
    y = np.array([m["mean_regret"] for m in native]) * 100
    lo = np.array([m["regret_ci95"][0] for m in native]) * 100
    hi = np.array([m["regret_ci95"][1] for m in native]) * 100
    ax.bar(
        np.arange(len(y)),
        y,
        color=[
            BLUE if m["name"] == "learned" else AMBER if m["name"] == "oracle-24" else "#b9c3cd"
            for m in native
        ],
        yerr=np.vstack((np.maximum(y - lo, 0), np.maximum(hi - y, 0))),
        capsize=3,
    )
    ax.set_xticks(np.arange(len(y)), [m["name"] for m in native], rotation=0, ha="center")
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_ylabel("Objective difference from native oracle (%)")
    ax.set_title("Held-out quality with circuit-cluster uncertainty", loc="left", fontweight="bold", pad=28)
    ax.text(
        0,
        1.02,
        "Four evaluations per search; oracle uses 24. Same 24 instances / 18 circuit clusters.",
        transform=ax.transAxes,
        fontsize=8,
    )
    ax.grid(axis="y", alpha=0.15)
    for ext in ("svg", "png"):
        fig.savefig(figures / f"heldout-regret.{ext}", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
    complete = [m for m in methods if m["name"] not in {"qmap", "bqskit"}]
    offsets = {
        "learned": (5, -17),
        "random": (5, 7),
        "heuristic": (-35, -15),
        "no-graph": (-28, 13),
        "qiskit-2": (-38, -17),
        "qiskit-3": (5, 7),
    }
    for method in complete:
        x, y = method["mean_wall_time_s"], method["mean_objective"]
        ax.scatter(
            x,
            y,
            s=65,
            color=BLUE
            if method["name"] == "learned"
            else AMBER
            if method["name"] == "oracle-24"
            else "#6a7b8b",
        )
        ax.annotate(
            method["name"],
            (x, y),
            xytext=offsets.get(method["name"], (5, 7)),
            textcoords="offset points",
            fontsize=8,
        )
    ax.margins(x=0.16, y=0.16)
    ax.set_xscale("log")
    ax.set_xticks([0.03, 0.05, 0.1, 0.2, 0.4], ["0.03", "0.05", "0.10", "0.20", "0.40"])
    ax.minorticks_off()
    ax.set_xlabel("Mean total wall time, including independent verification (seconds, log scale)")
    ax.set_ylabel("Mean hardware objective (lower is better)")
    ax.set_title("Compiler quality and CPU time, same circuit mix", loc="left", fontweight="bold", pad=28)
    ax.text(
        0,
        1.02,
        "Complete-coverage methods only. QMAP rejections and BQSKit subset excluded from this plot.",
        transform=ax.transAxes,
        fontsize=8,
    )
    ax.grid(alpha=0.15)
    for ext in ("svg", "png"):
        fig.savefig(figures / f"quality-time.{ext}", dpi=180)
    plt.close(fig)

    replay = [
        json.loads(line) for line in (root / "benchmarks" / "budget-replay.jsonl").read_text().splitlines()
    ]
    fig, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
    for name, color in (("learned", BLUE), ("random", "#6a7b8b"), ("heuristic", AMBER)):
        budgets = sorted({r["budget"] for r in replay if r["method"] == name})
        values = [
            np.mean([r["regret"] for r in replay if r["method"] == name and r["budget"] == b]) * 100
            for b in budgets
        ]
        ax.plot(budgets, values, marker="o", label=name, color=color)
    ax.set_yscale("symlog", linthresh=1, linscale=1)
    ax.set_yticks([0, 1, 10, 100, 1000], ["0", "1", "10", "100", "1000"])
    ax.set_xlabel("Number of native configurations evaluated")
    ax.set_ylabel("Mean regret against native oracle (%)")
    ax.set_title("Budget efficiency from saved exhaustive labels", loc="left", fontweight="bold", pad=28)
    ax.text(
        0,
        1.02,
        "Offline replay. Linear below 1%; logarithmic above. All candidates verified.",
        transform=ax.transAxes,
        fontsize=8,
    )
    ax.legend(frameon=False)
    ax.grid(alpha=0.15)
    for ext in ("svg", "png"):
        fig.savefig(figures / f"budget-efficiency.{ext}", dpi=180)
    plt.close(fig)

    noise = [r["noise"] for r in summary.get("noise", []) if "optimized_fidelity" in r["noise"]]
    if noise:
        fig, ax = plt.subplots(figsize=(6.5, 5), layout="constrained")
        ax.scatter(
            [r["input_fidelity"] for r in noise],
            [r["optimized_fidelity"] for r in noise],
            color=BLUE,
            alpha=0.8,
        )
        ax.plot([0, 1], [0, 1], color=INK, linewidth=0.8, linestyle="--")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("Qiskit level 0: zero-input distribution fidelity")
        ax.set_ylabel("QLOOM: zero-input distribution fidelity")
        ax.set_title("Synthetic noise comparison, no QPU data", loc="left", fontweight="bold", pad=28)
        ax.grid(alpha=0.15)
        for ext in ("svg", "png"):
            fig.savefig(figures / f"synthetic-noise.{ext}", dpi=180)
        plt.close(fig)
    print(f"Saved current result figures to {figures}")


if __name__ == "__main__":
    main()
